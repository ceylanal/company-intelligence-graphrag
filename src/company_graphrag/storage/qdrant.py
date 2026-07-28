"""Qdrant vector database connector and collection management."""

import time
from pathlib import Path
from typing import Any

import httpx
import structlog
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams

from company_graphrag.config import settings

logger = structlog.get_logger(__name__)

try:
    import portalocker

    _orig_portalocker_lock = portalocker.lock

    def _safe_portalocker_lock(file: Any, flags: Any, **kwargs: Any) -> Any:
        try:
            return _orig_portalocker_lock(file, flags, **kwargs)
        except portalocker.exceptions.LockException:
            return None

    portalocker.lock = _safe_portalocker_lock
except Exception:
    pass

DEFAULT_LOCAL_VECTOR_STORE_PATH = "data/vector_store/qdrant_db"


def get_qdrant_distance(distance_str: str) -> Distance:
    """Map string representation to Qdrant Distance enum."""
    dist_upper = distance_str.upper()
    if dist_upper == "COSINE":
        return Distance.COSINE
    elif dist_upper in ("DOT", "INNER"):
        return Distance.DOT
    elif dist_upper in ("EUCLID", "EUCLIDEAN"):
        return Distance.EUCLID
    return Distance.COSINE


_SHARED_LOCAL_CLIENTS: dict[str, QdrantClient] = {}


def _get_shared_local_client(path: str) -> QdrantClient:
    """Return process-wide singleton QdrantClient for embedded local mode."""
    canonical_path = str(Path(path).resolve())
    if canonical_path not in _SHARED_LOCAL_CLIENTS:
        logger.info("Initializing embedded local Qdrant storage", path=canonical_path)
        Path(canonical_path).mkdir(parents=True, exist_ok=True)
        _SHARED_LOCAL_CLIENTS[canonical_path] = QdrantClient(path=canonical_path)
    return _SHARED_LOCAL_CLIENTS[canonical_path]


class QdrantVectorStore:
    """Qdrant vector database storage client with automatic collection initialization and fallback."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        path: str | None = None,
    ) -> None:
        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key
        self.path = path
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        """Lazy-loaded QdrantClient instance with embedded local fallback."""
        if self._client is None:
            if self.path:
                self._client = _get_shared_local_client(self.path)
            else:
                is_qdrant_online = False
                try:
                    res = httpx.get(f"{self.url.rstrip('/')}/healthz", timeout=0.5)
                    if res.status_code == 200:
                        is_qdrant_online = True
                except Exception:
                    is_qdrant_online = False

                if is_qdrant_online:
                    kwargs: dict[str, Any] = {"url": self.url, "timeout": 15.0}
                    if self.api_key:
                        kwargs["api_key"] = self.api_key
                    try:
                        self._client = QdrantClient(**kwargs)
                    except Exception as err:
                        logger.warning(
                            "Qdrant REST client init failed, falling back to embedded local vector storage",
                            url=self.url,
                            error=str(err),
                            fallback_path=DEFAULT_LOCAL_VECTOR_STORE_PATH,
                        )
                        self._client = _get_shared_local_client(DEFAULT_LOCAL_VECTOR_STORE_PATH)
                else:
                    logger.warning(
                        "Qdrant REST connection unavailable, using embedded local vector storage",
                        url=self.url,
                        fallback_path=DEFAULT_LOCAL_VECTOR_STORE_PATH,
                    )
                    self._client = _get_shared_local_client(DEFAULT_LOCAL_VECTOR_STORE_PATH)

        return self._client

    def close(self) -> None:
        """Close QdrantClient instance for remote connections, keeping shared local singletons intact."""
        if self._client is not None:
            target_path = self.path or DEFAULT_LOCAL_VECTOR_STORE_PATH
            canonical_path = str(Path(target_path).resolve())
            if canonical_path not in _SHARED_LOCAL_CLIENTS:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None

    def ensure_collection(
        self,
        collection_name: str,
        vector_size: int = 384,
        distance_str: str = "Cosine",
        reset: bool = False,
    ) -> None:
        """Create Qdrant collection if it does not exist, or reset if requested."""
        distance = get_qdrant_distance(distance_str)

        try:
            exists = self.client.collection_exists(collection_name)
        except Exception as err:
            logger.error("Failed to check Qdrant collection existence", collection=collection_name, error=str(err))
            raise RuntimeError(f"Qdrant connection error: {err}") from err

        if exists and reset:
            logger.warning("Resetting Qdrant collection", collection=collection_name)
            self.client.delete_collection(collection_name)
            exists = False

        if not exists:
            logger.info(
                "Creating Qdrant collection",
                collection=collection_name,
                vector_size=vector_size,
                distance=distance_str,
            )
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance),
            )

    def upsert_points_batch(
        self,
        collection_name: str,
        points: list[PointStruct],
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> None:
        """Upsert a batch of points to Qdrant with automatic retry mechanism."""
        if not points:
            return

        for attempt in range(1, max_retries + 1):
            try:
                self.client.upsert(collection_name=collection_name, points=points, wait=True)
                return
            except (UnexpectedResponse, Exception) as err:
                logger.warning(
                    "Batch upsert failed, retrying",
                    collection=collection_name,
                    points_count=len(points),
                    attempt=attempt,
                    error=str(err),
                )
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to upsert points to Qdrant collection '{collection_name}' after {max_retries} attempts"
                    ) from err
                time.sleep(backoff_factor**attempt)

    def get_collection_info(self, collection_name: str) -> dict[str, Any]:
        """Return information and stats for a Qdrant collection."""
        if not self.client.collection_exists(collection_name):
            return {"exists": False, "points_count": 0, "vectors_count": 0}

        info = self.client.get_collection(collection_name)
        return {
            "exists": True,
            "status": str(info.status),
            "points_count": info.points_count or 0,
            "vectors_count": info.indexed_vectors_count or info.points_count or 0,
        }
