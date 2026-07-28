"""Idempotent, resumable entity and relation extraction from chunk JSONL records."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from string import Formatter
from typing import Any, Literal

from pydantic import ValidationError

from company_graphrag.chunking.models import ChunkRecord
from company_graphrag.graph.extraction.models import (
    CachedChunkResult,
    EntityExtractionRecord,
    ExtractionMetrics,
    ExtractionRunResult,
    RawEntityCandidate,
    RawRelationCandidate,
    RejectionReason,
    RejectionRecord,
    RelationExtractionRecord,
)
from company_graphrag.graph.extraction.provider import ExtractionProvider
from company_graphrag.graph.models import (
    NodeTypeConfig,
    RelationshipTypeConfig,
    normalize_id_component,
    stable_digest,
)
from company_graphrag.graph.schema import GraphSchemaManager


class GraphExtractionPipeline:
    """Validate untrusted extraction JSON and persist duplicate-free graph records."""

    def __init__(
        self,
        provider: ExtractionProvider,
        output_dir: Path,
        extraction_version: str,
        schema_manager: GraphSchemaManager | None = None,
    ) -> None:
        if not extraction_version.strip():
            raise ValueError("extraction_version must not be blank")
        self.provider = provider
        self.output_dir = Path(output_dir)
        self.extraction_version = extraction_version.strip()
        self.schema_manager = schema_manager or GraphSchemaManager()

        self.entities_path = self.output_dir / "entities.jsonl"
        self.relations_path = self.output_dir / "relations.jsonl"
        self.rejections_path = self.output_dir / "rejections.jsonl"
        self.checkpoint_path = self.output_dir / "checkpoint.json"
        self.metrics_path = self.output_dir / "metrics.json"

        version_key = normalize_id_component(self.extraction_version) or "version"
        version_digest = stable_digest(self.extraction_version, length=12)
        self.cache_dir = self.output_dir / ".cache" / f"{version_key}_{version_digest}"

    def run(self, input_path: Path, limit: int | None = None) -> ExtractionRunResult:
        """Process one chunk JSONL file or directory, optionally bounded by a safe limit."""
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1")
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Chunk input not found: {input_path}")
        return self._execute(self._iter_jsonl_items(input_path, limit))

    def run_chunks(
        self,
        chunks: Iterable[ChunkRecord],
        limit: int | None = None,
    ) -> ExtractionRunResult:
        """Process already-loaded chunks; useful for curated samples and tests."""
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1")

        def items() -> Iterator[ChunkRecord]:
            for index, chunk in enumerate(chunks):
                if limit is not None and index >= limit:
                    break
                yield chunk

        return self._execute(items())

    def _iter_jsonl_items(
        self,
        input_path: Path,
        limit: int | None,
    ) -> Iterator[ChunkRecord | RejectionRecord]:
        if input_path.is_file():
            paths = [input_path]
        else:
            output_root = self.output_dir.resolve()
            paths = [
                path for path in sorted(input_path.rglob("*.jsonl")) if not path.resolve().is_relative_to(output_root)
            ]
        seen = 0
        for path in paths:
            with path.open(encoding="utf-8") as jsonl_file:
                for line_number, line in enumerate(jsonl_file, start=1):
                    if not line.strip():
                        continue
                    if limit is not None and seen >= limit:
                        return
                    seen += 1
                    try:
                        yield ChunkRecord.model_validate_json(line)
                    except (ValidationError, ValueError) as error:
                        candidate: Any
                        try:
                            candidate = json.loads(line)
                        except json.JSONDecodeError:
                            candidate = line.rstrip("\n")
                        yield self._make_rejection(
                            chunk=None,
                            record_kind="chunk",
                            candidate_index=line_number - 1,
                            reason_code=RejectionReason.CHUNK_MODEL_INVALID,
                            reason=f"{path}:{line_number}: {error}",
                            candidate=candidate,
                            source_file=str(path),
                        )

    def _execute(
        self,
        items: Iterable[ChunkRecord | RejectionRecord],
    ) -> ExtractionRunResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for output_path in (self.entities_path, self.relations_path, self.rejections_path):
            output_path.touch(exist_ok=True)

        existing_entity_keys = self._load_entity_keys()
        existing_relation_keys = self._load_relation_keys()
        existing_rejection_ids = self._load_rejection_ids()
        checkpoint = self._load_checkpoint()

        run_entities: dict[tuple[str, str], EntityExtractionRecord] = {}
        run_relations: dict[tuple[str, str], RelationExtractionRecord] = {}
        run_rejections: dict[str, RejectionRecord] = {}
        processed_chunks = 0
        cache_hits = 0
        provider_calls = 0

        for item in items:
            processed_chunks += 1
            if isinstance(item, RejectionRecord):
                run_rejections.setdefault(item.rejection_id, item)
                self._append_rejection(item, existing_rejection_ids)
                continue

            chunk = item
            fingerprint = self._chunk_fingerprint(chunk)
            cached_result, cache_rejection = self._read_cache(chunk, fingerprint)
            if cached_result is not None:
                cache_hits += 1
                chunk_result = cached_result
            else:
                provider_calls += 1
                chunk_result = self._extract_chunk(chunk, fingerprint)
                if cache_rejection is not None:
                    chunk_result.rejections.insert(0, cache_rejection)
                self._write_cache(chunk_result)

            for entity in chunk_result.entities:
                run_entities.setdefault((entity.extraction_version, entity.id), entity)
                self._append_entity(entity, existing_entity_keys)
            for relation in chunk_result.relations:
                run_relations.setdefault((relation.extraction_version, relation.id), relation)
                self._append_relation(relation, existing_relation_keys)
            for rejection in chunk_result.rejections:
                run_rejections.setdefault(rejection.rejection_id, rejection)
                self._append_rejection(rejection, existing_rejection_ids)

            checkpoint_key = f"{self.extraction_version}:{chunk.chunk_id}"
            completed = checkpoint.setdefault("completed", {})
            completed[checkpoint_key] = {
                "chunk_fingerprint": fingerprint,
                "cache_file": str(self._cache_path(chunk.chunk_id).relative_to(self.output_dir)),
            }
            self._write_checkpoint(checkpoint)

        entities = list(run_entities.values())
        relations = list(run_relations.values())
        rejections = list(run_rejections.values())
        confidence_values = [record.confidence for record in entities] + [record.confidence for record in relations]
        metrics = ExtractionMetrics(
            processed_chunks=processed_chunks,
            entity_count=len(entities),
            relation_count=len(relations),
            rejected_count=len(rejections),
            entity_type_distribution=dict(sorted(Counter(record.type for record in entities).items())),
            relation_type_distribution=dict(sorted(Counter(record.type for record in relations).items())),
            average_confidence=round(
                sum(confidence_values) / len(confidence_values),
                4,
            )
            if confidence_values
            else 0.0,
            cache_hits=cache_hits,
            provider_calls=provider_calls,
        )
        self._write_json_atomic(self.metrics_path, metrics.model_dump(mode="json"))
        if not self.checkpoint_path.exists():
            self._write_checkpoint(checkpoint)

        return ExtractionRunResult(
            metrics=metrics,
            entities=entities,
            relations=relations,
            rejections=rejections,
            entities_path=self.entities_path,
            relations_path=self.relations_path,
            rejections_path=self.rejections_path,
            checkpoint_path=self.checkpoint_path,
            metrics_path=self.metrics_path,
        )

    def _extract_chunk(self, chunk: ChunkRecord, fingerprint: str) -> CachedChunkResult:
        try:
            raw_response = self.provider.extract(
                chunk,
                self.schema_manager.config,
                self.extraction_version,
            )
        except Exception as error:
            return CachedChunkResult(
                chunk_id=chunk.chunk_id,
                chunk_fingerprint=fingerprint,
                schema_version=self.schema_manager.config.version,
                extraction_version=self.extraction_version,
                rejections=[
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="chunk",
                        candidate_index=None,
                        reason_code=RejectionReason.PROVIDER_ERROR,
                        reason=f"Extraction provider raised {type(error).__name__}: {error}",
                        candidate=None,
                    )
                ],
            )

        try:
            decoded = json.loads(raw_response)
        except (json.JSONDecodeError, TypeError) as error:
            return CachedChunkResult(
                chunk_id=chunk.chunk_id,
                chunk_fingerprint=fingerprint,
                schema_version=self.schema_manager.config.version,
                extraction_version=self.extraction_version,
                rejections=[
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="chunk",
                        candidate_index=None,
                        reason_code=RejectionReason.LLM_JSON_INVALID,
                        reason=f"Provider output is not valid JSON: {error}",
                        candidate=raw_response,
                    )
                ],
            )

        if (
            not isinstance(decoded, dict)
            or set(decoded) != {"entities", "relations"}
            or not isinstance(decoded["entities"], list)
            or not isinstance(decoded["relations"], list)
        ):
            return CachedChunkResult(
                chunk_id=chunk.chunk_id,
                chunk_fingerprint=fingerprint,
                schema_version=self.schema_manager.config.version,
                extraction_version=self.extraction_version,
                rejections=[
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="chunk",
                        candidate_index=None,
                        reason_code=RejectionReason.LLM_SHAPE_INVALID,
                        reason="Provider JSON must contain exactly list fields 'entities' and 'relations'.",
                        candidate=decoded,
                    )
                ],
            )

        entities: list[EntityExtractionRecord] = []
        relations: list[RelationExtractionRecord] = []
        rejections: list[RejectionRecord] = []
        ref_to_entity: dict[str, EntityExtractionRecord] = {}
        entity_ids: set[str] = set()

        for index, raw_candidate in enumerate(decoded["entities"]):
            try:
                entity_candidate = RawEntityCandidate.model_validate(raw_candidate)
            except ValidationError as validation_error:
                rejections.append(
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="entity",
                        candidate_index=index,
                        reason_code=RejectionReason.ENTITY_MODEL_INVALID,
                        reason=str(validation_error),
                        candidate=raw_candidate,
                    )
                )
                continue

            if entity_candidate.ref in ref_to_entity:
                rejections.append(
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="entity",
                        candidate_index=index,
                        reason_code=RejectionReason.DUPLICATE_REF,
                        reason=f"Duplicate entity ref '{entity_candidate.ref}' within one provider response.",
                        candidate=raw_candidate,
                    )
                )
                continue

            entity, entity_error = self._validate_entity_candidate(chunk, entity_candidate)
            if entity_error is not None:
                rejections.append(
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="entity",
                        candidate_index=index,
                        reason_code=entity_error[0],
                        reason=entity_error[1],
                        candidate=raw_candidate,
                    )
                )
                continue

            assert entity is not None
            ref_to_entity[entity_candidate.ref] = entity
            if entity.id not in entity_ids:
                entities.append(entity)
                entity_ids.add(entity.id)

        relation_ids: set[str] = set()
        for index, raw_candidate in enumerate(decoded["relations"]):
            try:
                relation_candidate = RawRelationCandidate.model_validate(raw_candidate)
            except ValidationError as validation_error:
                rejections.append(
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="relation",
                        candidate_index=index,
                        reason_code=RejectionReason.RELATION_MODEL_INVALID,
                        reason=str(validation_error),
                        candidate=raw_candidate,
                    )
                )
                continue

            relation, relation_error = self._validate_relation_candidate(
                chunk,
                relation_candidate,
                ref_to_entity,
            )
            if relation_error is not None:
                rejections.append(
                    self._make_rejection(
                        chunk=chunk,
                        record_kind="relation",
                        candidate_index=index,
                        reason_code=relation_error[0],
                        reason=relation_error[1],
                        candidate=raw_candidate,
                    )
                )
                continue

            assert relation is not None
            if relation.id not in relation_ids:
                relations.append(relation)
                relation_ids.add(relation.id)

        return CachedChunkResult(
            chunk_id=chunk.chunk_id,
            chunk_fingerprint=fingerprint,
            schema_version=self.schema_manager.config.version,
            extraction_version=self.extraction_version,
            entities=entities,
            relations=relations,
            rejections=rejections,
        )

    def _validate_entity_candidate(
        self,
        chunk: ChunkRecord,
        candidate: RawEntityCandidate,
    ) -> tuple[EntityExtractionRecord | None, tuple[RejectionReason, str] | None]:
        if candidate.type not in self.schema_manager.get_node_types():
            return None, (
                RejectionReason.UNKNOWN_NODE_TYPE,
                f"Node type '{candidate.type}' is not declared in schema.yaml.",
            )
        provenance_error = self._candidate_provenance_error(chunk, candidate)
        if provenance_error:
            return None, (RejectionReason.PROVENANCE_MISMATCH, provenance_error)
        if candidate.evidence_text not in chunk.text:
            return None, (
                RejectionReason.EVIDENCE_NOT_IN_CHUNK,
                "evidence_text is not an exact substring of the source chunk.",
            )

        node_config = self.schema_manager.get_node_types()[candidate.type]
        properties, property_error = self._enrich_properties(
            chunk,
            candidate.properties,
            node_config,
        )
        if property_error:
            return None, (RejectionReason.PROVENANCE_MISMATCH, property_error)

        try:
            properties["id"] = self._generate_node_id(candidate.type, properties, node_config)
        except (KeyError, ValueError) as error:
            return None, (
                RejectionReason.SCHEMA_VALIDATION_FAILED,
                f"Cannot generate deterministic node ID: {error}",
            )

        validation_errors = self.schema_manager.validate_node_dict(candidate.type, properties)
        if validation_errors:
            return None, (
                RejectionReason.SCHEMA_VALIDATION_FAILED,
                "; ".join(validation_errors),
            )

        return (
            EntityExtractionRecord(
                id=str(properties["id"]),
                type=candidate.type,
                canonical_name=candidate.canonical_name,
                properties=properties,
                source_chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                page_number=chunk.page_number,
                evidence_text=candidate.evidence_text,
                confidence=candidate.confidence,
                extraction_version=self.extraction_version,
            ),
            None,
        )

    def _validate_relation_candidate(
        self,
        chunk: ChunkRecord,
        candidate: RawRelationCandidate,
        ref_to_entity: dict[str, EntityExtractionRecord],
    ) -> tuple[RelationExtractionRecord | None, tuple[RejectionReason, str] | None]:
        if candidate.type not in self.schema_manager.get_relationship_types():
            return None, (
                RejectionReason.UNKNOWN_RELATION_TYPE,
                f"Relationship type '{candidate.type}' is not declared in schema.yaml.",
            )
        provenance_error = self._candidate_provenance_error(chunk, candidate)
        if provenance_error:
            return None, (RejectionReason.PROVENANCE_MISMATCH, provenance_error)
        if candidate.evidence_text not in chunk.text:
            return None, (
                RejectionReason.EVIDENCE_NOT_IN_CHUNK,
                "evidence_text is not an exact substring of the source chunk.",
            )
        if candidate.source_ref not in ref_to_entity or candidate.target_ref not in ref_to_entity:
            missing = [ref for ref in (candidate.source_ref, candidate.target_ref) if ref not in ref_to_entity]
            return None, (
                RejectionReason.ENTITY_REFERENCE_NOT_FOUND,
                f"Relation refers to missing or rejected entity refs: {missing}.",
            )

        source = ref_to_entity[candidate.source_ref]
        target = ref_to_entity[candidate.target_ref]
        relationship_config = self.schema_manager.get_relationship_types()[candidate.type]
        properties, property_error = self._enrich_properties(
            chunk,
            candidate.properties,
            relationship_config,
        )
        if property_error:
            return None, (RejectionReason.PROVENANCE_MISMATCH, property_error)

        try:
            properties["id"] = self._generate_relationship_id(
                candidate.type,
                source.id,
                target.id,
                properties,
                relationship_config,
            )
        except (KeyError, ValueError) as error:
            return None, (
                RejectionReason.SCHEMA_VALIDATION_FAILED,
                f"Cannot generate deterministic relationship ID: {error}",
            )

        validation_errors = self.schema_manager.validate_relationship(
            candidate.type,
            source.type,
            target.type,
            properties,
        )
        if validation_errors:
            return None, (
                RejectionReason.SCHEMA_VALIDATION_FAILED,
                "; ".join(validation_errors),
            )

        return (
            RelationExtractionRecord(
                id=str(properties["id"]),
                type=candidate.type,
                source_entity_id=source.id,
                target_entity_id=target.id,
                properties=properties,
                source_chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                page_number=chunk.page_number,
                evidence_text=candidate.evidence_text,
                confidence=candidate.confidence,
                extraction_version=self.extraction_version,
            ),
            None,
        )

    @staticmethod
    def _candidate_provenance_error(
        chunk: ChunkRecord,
        candidate: RawEntityCandidate | RawRelationCandidate,
    ) -> str | None:
        mismatches: list[str] = []
        if candidate.source_chunk_id != chunk.chunk_id:
            mismatches.append(f"source_chunk_id={candidate.source_chunk_id!r}, expected {chunk.chunk_id!r}")
        if candidate.source_file != chunk.source_file:
            mismatches.append(f"source_file={candidate.source_file!r}, expected {chunk.source_file!r}")
        if candidate.page_number != chunk.page_number:
            mismatches.append(f"page_number={candidate.page_number}, expected {chunk.page_number}")
        return "; ".join(mismatches) if mismatches else None

    def _enrich_properties(
        self,
        chunk: ChunkRecord,
        raw_properties: dict[str, Any],
        config: NodeTypeConfig | RelationshipTypeConfig,
    ) -> tuple[dict[str, Any], str | None]:
        properties = dict(raw_properties)
        properties.pop("id", None)
        trusted_values: dict[str, Any] = {
            "source_report_id": f"report:{chunk.document_id}",
            "source_chunk_id": chunk.chunk_id,
            "source_page": chunk.page_number,
        }
        for field_name, trusted_value in trusted_values.items():
            if field_name not in config.all_properties:
                continue
            if field_name in properties and properties[field_name] != trusted_value:
                return properties, (
                    f"Graph property {field_name}={properties[field_name]!r}, expected trusted value {trusted_value!r}."
                )
            properties[field_name] = trusted_value
        return properties, None

    @staticmethod
    def _generate_node_id(
        node_type: str,
        properties: dict[str, Any],
        config: NodeTypeConfig,
    ) -> str:
        template_values = dict(properties)
        company_id = str(properties.get("company_id", ""))
        ticker = properties.get("ticker")
        if not ticker and company_id.startswith("company:"):
            ticker = company_id.split(":", 1)[1]
        template_values["TICKER"] = ticker

        if config.id_generation.strategy == "template":
            required_fields = [
                field_name for _, field_name, _, _ in Formatter().parse(config.id_generation.pattern) if field_name
            ]
            missing = [field_name for field_name in required_fields if not template_values.get(field_name)]
            if missing:
                raise KeyError(f"missing template inputs {missing}")
            return config.id_generation.pattern.format_map(template_values)

        inputs = [str(properties[input_name]) for input_name in config.id_generation.inputs]
        digest_length = config.id_generation.digest_length or 24
        digest = stable_digest(*inputs, length=digest_length)
        digest_token = f"{{sha256_{digest_length}}}"
        if digest_token not in config.id_generation.pattern:
            raise ValueError(f"ID pattern does not contain {digest_token}")
        pattern = config.id_generation.pattern.replace(digest_token, digest)
        if "{TICKER}" in pattern:
            if not ticker:
                raise KeyError("missing TICKER")
            pattern = pattern.replace("{TICKER}", str(ticker))
        return pattern

    @staticmethod
    def _generate_relationship_id(
        relationship_type: str,
        source_id: str,
        target_id: str,
        properties: dict[str, Any],
        config: RelationshipTypeConfig,
    ) -> str:
        context = {
            "relationship_type": relationship_type,
            "source_id": source_id,
            "target_id": target_id,
            **properties,
        }
        inputs = [str(context[input_name]) for input_name in config.id_generation.inputs]
        digest_length = config.id_generation.digest_length or 24
        digest = stable_digest(*inputs, length=digest_length)
        digest_token = f"{{sha256_{digest_length}}}"
        if digest_token not in config.id_generation.pattern:
            raise ValueError(f"ID pattern does not contain {digest_token}")
        return config.id_generation.pattern.replace(digest_token, digest)

    def _read_cache(
        self,
        chunk: ChunkRecord,
        fingerprint: str,
    ) -> tuple[CachedChunkResult | None, RejectionRecord | None]:
        cache_path = self._cache_path(chunk.chunk_id)
        if not cache_path.exists():
            return None, None
        try:
            cached = CachedChunkResult.model_validate_json(cache_path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError) as error:
            return None, self._make_rejection(
                chunk=chunk,
                record_kind="cache",
                candidate_index=None,
                reason_code=RejectionReason.CACHE_INVALID,
                reason=f"Invalid cache file {cache_path}: {error}",
                candidate=None,
            )
        if (
            cached.chunk_id != chunk.chunk_id
            or cached.chunk_fingerprint != fingerprint
            or cached.schema_version != self.schema_manager.config.version
            or cached.extraction_version != self.extraction_version
        ):
            return None, None
        return cached, None

    def _write_cache(self, result: CachedChunkResult) -> None:
        self._write_json_atomic(
            self._cache_path(result.chunk_id),
            result.model_dump(mode="json"),
        )

    def _cache_path(self, chunk_id: str) -> Path:
        safe_chunk_id = normalize_id_component(chunk_id)
        return self.cache_dir / f"{safe_chunk_id}.json"

    @staticmethod
    def _chunk_fingerprint(chunk: ChunkRecord) -> str:
        canonical = json.dumps(
            chunk.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return stable_digest(canonical, length=64)

    def _load_checkpoint(self) -> dict[str, Any]:
        default: dict[str, Any] = {
            "schema_version": self.schema_manager.config.version,
            "completed": {},
        }
        if not self.checkpoint_path.exists():
            return default
        try:
            checkpoint = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("completed"), dict):
            return default
        if checkpoint.get("schema_version") != self.schema_manager.config.version:
            return default
        return checkpoint

    def _write_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self._write_json_atomic(self.checkpoint_path, checkpoint)

    def _load_entity_keys(self) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        if not self.entities_path.exists():
            return keys
        with self.entities_path.open(encoding="utf-8") as jsonl_file:
            for line_number, line in enumerate(jsonl_file, start=1):
                if not line.strip():
                    continue
                try:
                    record = EntityExtractionRecord.model_validate_json(line)
                except ValidationError as error:
                    raise RuntimeError(
                        f"Invalid existing entity output at {self.entities_path}:{line_number}: {error}"
                    ) from error
                keys.add((record.extraction_version, record.id))
        return keys

    def _load_relation_keys(self) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        if not self.relations_path.exists():
            return keys
        with self.relations_path.open(encoding="utf-8") as jsonl_file:
            for line_number, line in enumerate(jsonl_file, start=1):
                if not line.strip():
                    continue
                try:
                    record = RelationExtractionRecord.model_validate_json(line)
                except ValidationError as error:
                    raise RuntimeError(
                        f"Invalid existing relation output at {self.relations_path}:{line_number}: {error}"
                    ) from error
                keys.add((record.extraction_version, record.id))
        return keys

    def _load_rejection_ids(self) -> set[str]:
        keys: set[str] = set()
        if not self.rejections_path.exists():
            return keys
        with self.rejections_path.open(encoding="utf-8") as jsonl_file:
            for line_number, line in enumerate(jsonl_file, start=1):
                if not line.strip():
                    continue
                try:
                    record = RejectionRecord.model_validate_json(line)
                except ValidationError as error:
                    raise RuntimeError(
                        f"Invalid existing rejection output at {self.rejections_path}:{line_number}: {error}"
                    ) from error
                keys.add(record.rejection_id)
        return keys

    def _append_entity(
        self,
        record: EntityExtractionRecord,
        existing_keys: set[tuple[str, str]],
    ) -> None:
        key = (record.extraction_version, record.id)
        if key in existing_keys:
            return
        self._append_jsonl(self.entities_path, record.model_dump_json())
        existing_keys.add(key)

    def _append_relation(
        self,
        record: RelationExtractionRecord,
        existing_keys: set[tuple[str, str]],
    ) -> None:
        key = (record.extraction_version, record.id)
        if key in existing_keys:
            return
        self._append_jsonl(self.relations_path, record.model_dump_json())
        existing_keys.add(key)

    def _append_rejection(
        self,
        record: RejectionRecord,
        existing_ids: set[str],
    ) -> None:
        if record.rejection_id in existing_ids:
            return
        self._append_jsonl(self.rejections_path, record.model_dump_json())
        existing_ids.add(record.rejection_id)

    @staticmethod
    def _append_jsonl(path: Path, serialized_record: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as jsonl_file:
            jsonl_file.write(serialized_record + "\n")

    @staticmethod
    def _write_json_atomic(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)

    def _make_rejection(
        self,
        *,
        chunk: ChunkRecord | None,
        record_kind: Literal["chunk", "entity", "relation", "cache"],
        candidate_index: int | None,
        reason_code: RejectionReason,
        reason: str,
        candidate: Any,
        source_file: str | None = None,
    ) -> RejectionRecord:
        chunk_id = chunk.chunk_id if chunk else None
        canonical_candidate = json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        rejection_id = "rejection:" + stable_digest(
            self.extraction_version,
            chunk_id or "",
            record_kind,
            str(candidate_index),
            reason_code.value,
            reason,
            canonical_candidate,
            length=24,
        )
        return RejectionRecord(
            rejection_id=rejection_id,
            chunk_id=chunk_id,
            record_kind=record_kind,
            candidate_index=candidate_index,
            reason_code=reason_code,
            reason=reason,
            candidate=candidate,
            source_file=source_file or (chunk.source_file if chunk else None),
            page_number=chunk.page_number if chunk else None,
            extraction_version=self.extraction_version,
        )
