"""Neo4j Storage Client and In-Memory Fallback Graph Store."""

from typing import Any

from structlog import get_logger

from company_graphrag.config import settings

try:
    from neo4j import Driver, GraphDatabase

    HAS_NEO4J_DRIVER = True
except ImportError:
    HAS_NEO4J_DRIVER = False
    Driver = Any  # type: ignore[misc,assignment]

logger = get_logger(__name__)

DEFAULT_NEO4J_URI = "bolt://localhost:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = "password"
DEFAULT_NEO4J_DATABASE = "neo4j"


class MockNeo4jStore:
    """In-memory graph database mock for testing and offline fallback."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}  # node_id -> {id, labels: set, properties: dict}
        self.relationships: dict[
            str, dict[str, Any]
        ] = {}  # rel_id -> {id, type, source_id, target_id, properties: dict}
        self.constraints: set[str] = set()

    def execute_cypher(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Mock execution of basic Cypher queries (DDL, UNWIND MERGE, MATCH COUNT)."""
        params = parameters or {}

        # DDL Constraints / Indexes
        if (
            query.strip().startswith("CREATE CONSTRAINT")
            or query.strip().startswith("CREATE INDEX")
            or query.strip().startswith("CREATE FULLTEXT INDEX")
        ):
            self.constraints.add(query.strip())
            return []

        # Batch Node MERGE (UNWIND $batch AS item ...)
        if "UNWIND $batch AS item" in query and "MERGE (n:" in query:
            # Extract label from MERGE (n:Label {id: item.id})
            label = query.split("MERGE (n:")[1].split(" ")[0].split("{")[0]
            batch = params.get("batch", [])
            for item in batch:
                node_id = str(item.get("id"))
                if not node_id:
                    continue
                if node_id not in self.nodes:
                    self.nodes[node_id] = {
                        "id": node_id,
                        "labels": {label},
                        "properties": dict(item),
                    }
                else:
                    self.nodes[node_id]["labels"].add(label)
                    self.nodes[node_id]["properties"].update(dict(item))
            return []

        # Batch Relation MERGE (UNWIND $batch AS item ...)
        if "UNWIND $batch AS item" in query and "MERGE (source)-[r:" in query:
            rel_type = query.split("MERGE (source)-[r:")[1].split(" ")[0].split("]")[0].split("{")[0]
            batch = params.get("batch", [])
            for item in batch:
                rel_id = str(item.get("id"))
                src_id = str(item.get("source_id"))
                tgt_id = str(item.get("target_id"))
                if not rel_id or not src_id or not tgt_id:
                    continue
                if rel_id not in self.relationships:
                    self.relationships[rel_id] = {
                        "id": rel_id,
                        "type": rel_type,
                        "source_id": src_id,
                        "target_id": tgt_id,
                        "properties": dict(item),
                    }
                else:
                    self.relationships[rel_id]["properties"].update(dict(item))
            return []

        # Verification Queries: Count Nodes by Label
        if "MATCH (n) RETURN labels(n)[0]" in query or ("labels(n)" in query and "count(n)" in query):
            label_counts: dict[str, int] = {}
            for n in self.nodes.values():
                for lbl in n["labels"]:
                    label_counts[lbl] = label_counts.get(lbl, 0) + 1
            return [{"label": lbl, "count": c} for lbl, c in label_counts.items()]

        # Verification Queries: Count Relations by Type
        if "MATCH ()-[r]->()" in query or ("type(r)" in query and "count(r)" in query):
            type_counts: dict[str, int] = {}
            for r in self.relationships.values():
                t = r["type"]
                type_counts[t] = type_counts.get(t, 0) + 1
            return [{"rel_type": t, "count": c} for t, c in type_counts.items()]

        # Verification Queries: Count Orphan / Unconnected Nodes
        if "NOT (n)-[]-()" in query or "orphan" in query.lower():
            connected_ids = set()
            for r in self.relationships.values():
                connected_ids.add(r["source_id"])
                connected_ids.add(r["target_id"])
            orphans = [nid for nid in self.nodes if nid not in connected_ids]
            return [{"orphan_count": len(orphans)}]

        # Delete Queries (MATCH ()-[r {id: $id}]->() DELETE r or MATCH (n {id: $id}) DELETE n)
        if "DELETE" in query:
            item_id = str(params.get("id"))
            if item_id in self.relationships:
                del self.relationships[item_id]
            if item_id in self.nodes:
                del self.nodes[item_id]
            return []

        # Property SET Queries (MATCH (n {id: $id}) SET ...)
        if "SET " in query:
            item_id = str(params.get("id"))
            if item_id in self.nodes:
                self.nodes[item_id]["properties"].update(params)
            if item_id in self.relationships:
                self.relationships[item_id]["properties"].update(params)
            return []

        return []


class Neo4jGraphStore:
    """Production Neo4j Database Store with automatic fallback to mock in-memory store."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        mock_mode: bool = False,
        allow_fallback: bool = True,
    ) -> None:
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_username
        self.password = password if password is not None else settings.neo4j_password
        self.database = database or settings.neo4j_database
        self.mock_mode = mock_mode
        self.allow_fallback = allow_fallback
        self._driver: Driver | None = None
        self._mock_store: MockNeo4jStore | None = None

        if not mock_mode and HAS_NEO4J_DRIVER:
            is_cloud_uri = self.uri.startswith("neo4j+s://") or self.uri.startswith("neo4j://") or getattr(settings, "neo4j_use_cloud", False)
            if is_cloud_uri:
                try:
                    drv = GraphDatabase.driver(self.uri, auth=(self.user, self.password), connection_timeout=10.0)
                    drv.verify_connectivity()
                    self._driver = drv
                    logger.info("Connected to live cloud Neo4j database", uri=self.uri)
                except Exception as err:
                    if not self.allow_fallback:
                        raise ConnectionError(
                            "Cloud Neo4j connectivity failed while fallback is disabled."
                        ) from err
                    logger.warning(
                        "Cloud Neo4j connection failed, falling back to mock graph storage",
                        uri=self.uri,
                        error=str(err),
                    )
                    self.mock_mode = True
                    self._mock_store = MockNeo4jStore()
            else:
                import httpx

                is_neo4j_online = False
                try:
                    auth_args: Any = (self.user, self.password) if self.password else None
                    res = httpx.get(settings.effective_neo4j_http_url, auth=auth_args, timeout=0.5, follow_redirects=True)
                    if res.status_code in (200, 301, 302):
                        is_neo4j_online = True
                except Exception:
                    is_neo4j_online = False

                if is_neo4j_online:
                    try:
                        drv = GraphDatabase.driver(self.uri, auth=(self.user, self.password), connection_timeout=1.0)
                        drv.verify_connectivity()
                        self._driver = drv
                        logger.info("Connected to live Neo4j database", uri=self.uri)
                    except Exception as err:
                        if not self.allow_fallback:
                            raise ConnectionError(
                                "Neo4j connectivity failed while fallback is disabled."
                            ) from err
                        logger.warning(
                            "Neo4j connection failed, falling back to mock graph storage",
                            uri=self.uri,
                            error=str(err),
                        )
                        self.mock_mode = True
                        self._mock_store = MockNeo4jStore()
                else:
                    if not self.allow_fallback:
                        raise ConnectionError("Neo4j is unavailable while fallback is disabled.")
                    logger.warning(
                        "Neo4j connection unavailable, using mock graph storage fallback",
                        uri=self.uri,
                    )
                    self.mock_mode = True
                    self._mock_store = MockNeo4jStore()
        else:
            self.mock_mode = True
            self._mock_store = MockNeo4jStore()

    def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run Cypher query and return list of result record dictionaries."""
        if self.mock_mode or self._driver is None:
            assert self._mock_store is not None
            return self._mock_store.execute_cypher(query, parameters)

        params = parameters or {}
        with self._driver.session(database=self.database) as session:
            result = session.run(query, params)
            return [record.data() for record in result]

        return []

    def execute_batch(self, cypher: str, batch: list[dict[str, Any]]) -> int:
        """Execute batched Cypher statement using UNWIND $batch AS item."""
        if not batch:
            return 0

        self.run_query(cypher, {"batch": batch})
        return len(batch)

    def close(self) -> None:
        """Close Neo4j driver connection."""
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
