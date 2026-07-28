"""Extraction-provider interface and deterministic provider used by tests and samples."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from company_graphrag.chunking.models import ChunkRecord
from company_graphrag.graph.models import GraphSchemaConfig


class ExtractionProvider(Protocol):
    """Interface implemented by LLM adapters or deterministic extractors."""

    def extract(
        self,
        chunk: ChunkRecord,
        schema: GraphSchemaConfig,
        extraction_version: str,
    ) -> str:
        """Return one JSON object with `entities` and `relations` arrays."""
        ...


class StaticExtractionProvider:
    """Deterministic, network-free provider keyed by chunk_id."""

    def __init__(self, responses: Mapping[str, str | dict[str, Any]]) -> None:
        self.responses = dict(responses)
        self.call_count = 0

    def extract(
        self,
        chunk: ChunkRecord,
        schema: GraphSchemaConfig,
        extraction_version: str,
    ) -> str:
        del schema, extraction_version
        self.call_count += 1
        response = self.responses.get(chunk.chunk_id, {"entities": [], "relations": []})
        if isinstance(response, str):
            return response
        return json.dumps(response, ensure_ascii=False, sort_keys=True)
