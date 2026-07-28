"""Typed graph schema configuration and first-version graph entity models."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictSchemaModel(BaseModel):
    """Base class that rejects misspelled or unsupported schema keys."""

    model_config = ConfigDict(extra="forbid")


class PropertyType(StrEnum):
    """Scalar property types supported by the first graph schema."""

    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    STRING_LIST = "STRING_LIST"


class PropertyDefinition(StrictSchemaModel):
    """Machine-readable definition of a Neo4j property."""

    type: PropertyType
    description: str
    allowed_values: list[str] | None = None
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None


class IdGenerationConfig(StrictSchemaModel):
    """Deterministic identifier recipe for a node or relationship."""

    strategy: Literal["template", "sha256"]
    pattern: str
    inputs: list[str]
    normalization: str
    digest_length: int | None = Field(default=None, ge=8, le=64)
    example: str


class ProvenanceConfig(StrictSchemaModel):
    """Citation contract for a node or relationship."""

    mode: Literal["CANONICAL", "DOCUMENT", "CHUNK"]
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    description: str


class NodeTypeConfig(StrictSchemaModel):
    """Configuration for one graph node label."""

    description: str
    primary_key: str
    id_generation: IdGenerationConfig
    required_properties: dict[str, PropertyDefinition]
    optional_properties: dict[str, PropertyDefinition] = Field(default_factory=dict)
    provenance: ProvenanceConfig

    @property
    def id_pattern(self) -> str:
        """Compatibility accessor used by the existing CLI."""
        return self.id_generation.pattern

    @property
    def all_properties(self) -> dict[str, PropertyDefinition]:
        """Return required and optional properties as one mapping."""
        return {**self.required_properties, **self.optional_properties}


class RelationshipTypeConfig(StrictSchemaModel):
    """Configuration for one directed graph relationship type."""

    description: str
    source: str | list[str]
    target: str
    cardinality: Literal["ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY"]
    id_generation: IdGenerationConfig
    required_properties: dict[str, PropertyDefinition]
    optional_properties: dict[str, PropertyDefinition] = Field(default_factory=dict)
    provenance: ProvenanceConfig

    @property
    def source_labels(self) -> tuple[str, ...]:
        """Return source labels in a uniform form."""
        return (self.source,) if isinstance(self.source, str) else tuple(self.source)

    @property
    def all_properties(self) -> dict[str, PropertyDefinition]:
        """Return required and optional properties as one mapping."""
        return {**self.required_properties, **self.optional_properties}


class SourceContractConfig(StrictSchemaModel):
    """Mapping from the current ingestion/chunk pipeline into graph provenance."""

    report_manifest: dict[str, str]
    chunk_metadata: dict[str, str]
    extraction_rules: list[str]


class Neo4jConstraintConfig(StrictSchemaModel):
    """Neo4j node constraint declaration."""

    name: str
    entity: Literal["NODE"] = "NODE"
    label: str
    properties: list[str] = Field(min_length=1)
    kind: Literal["UNIQUE"] = "UNIQUE"


class Neo4jIndexConfig(StrictSchemaModel):
    """Neo4j range or full-text index declaration."""

    name: str
    entity: Literal["NODE", "RELATIONSHIP"]
    kind: Literal["RANGE", "FULLTEXT"]
    labels: list[str] = Field(default_factory=list)
    relationship_type: str | None = None
    properties: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> Neo4jIndexConfig:
        """Require exactly the target fields needed by the selected entity."""
        if self.entity == "NODE" and not self.labels:
            raise ValueError(f"Neo4j node index '{self.name}' must declare labels")
        if self.entity == "RELATIONSHIP" and not self.relationship_type:
            raise ValueError(f"Neo4j relationship index '{self.name}' must declare relationship_type")
        if self.kind == "RANGE" and self.entity == "NODE" and len(self.labels) != 1:
            raise ValueError(f"Neo4j range index '{self.name}' must target exactly one node label")
        return self


class Neo4jPlanConfig(StrictSchemaModel):
    """Database compatibility, constraints, indexes, and application-only rules."""

    minimum_version: str
    edition: Literal["community", "enterprise"]
    constraints: list[Neo4jConstraintConfig]
    indexes: list[Neo4jIndexConfig]
    application_enforced_rules: list[str]


class GraphSchemaConfig(StrictSchemaModel):
    """Complete graph ontology and physical Neo4j plan."""

    version: str
    domain: str
    description: str
    source_contract: SourceContractConfig
    node_types: dict[str, NodeTypeConfig]
    relationship_types: dict[str, RelationshipTypeConfig]
    neo4j: Neo4jPlanConfig

    @model_validator(mode="after")
    def validate_internal_references(self) -> GraphSchemaConfig:
        """Reject dangling labels, fields, ID inputs, and physical-plan references."""
        node_labels = set(self.node_types)
        relationship_names = set(self.relationship_types)
        context_inputs = {"relationship_type", "source_id", "target_id"}

        for label, node in self.node_types.items():
            overlap = set(node.required_properties) & set(node.optional_properties)
            if overlap:
                raise ValueError(f"Node '{label}' declares properties twice: {sorted(overlap)}")
            if node.primary_key not in node.required_properties:
                raise ValueError(f"Node '{label}' primary key '{node.primary_key}' must be required")
            missing_inputs = set(node.id_generation.inputs) - set(node.all_properties)
            if missing_inputs:
                raise ValueError(f"Node '{label}' ID inputs are undeclared: {sorted(missing_inputs)}")
            _validate_provenance_fields(f"Node '{label}'", node.provenance, node)

        for name, relationship in self.relationship_types.items():
            unknown_sources = set(relationship.source_labels) - node_labels
            if unknown_sources:
                raise ValueError(f"Relationship '{name}' has unknown source labels: {sorted(unknown_sources)}")
            if relationship.target not in node_labels:
                raise ValueError(f"Relationship '{name}' has unknown target label '{relationship.target}'")
            overlap = set(relationship.required_properties) & set(relationship.optional_properties)
            if overlap:
                raise ValueError(f"Relationship '{name}' declares properties twice: {sorted(overlap)}")
            missing_inputs = set(relationship.id_generation.inputs) - set(relationship.all_properties) - context_inputs
            if missing_inputs:
                raise ValueError(f"Relationship '{name}' ID inputs are undeclared: {sorted(missing_inputs)}")
            _validate_provenance_fields(f"Relationship '{name}'", relationship.provenance, relationship)

        seen_ddl_names: set[str] = set()
        for constraint in self.neo4j.constraints:
            if constraint.name in seen_ddl_names:
                raise ValueError(f"Duplicate Neo4j DDL name '{constraint.name}'")
            seen_ddl_names.add(constraint.name)
            if constraint.label not in node_labels:
                raise ValueError(f"Constraint '{constraint.name}' targets unknown label '{constraint.label}'")
            unknown = set(constraint.properties) - set(self.node_types[constraint.label].all_properties)
            if unknown:
                raise ValueError(f"Constraint '{constraint.name}' uses undeclared properties: {sorted(unknown)}")

        for index in self.neo4j.indexes:
            if index.name in seen_ddl_names:
                raise ValueError(f"Duplicate Neo4j DDL name '{index.name}'")
            seen_ddl_names.add(index.name)
            if index.entity == "NODE":
                unknown_labels = set(index.labels) - node_labels
                if unknown_labels:
                    raise ValueError(f"Index '{index.name}' has unknown labels: {sorted(unknown_labels)}")
                declared = set().union(*(set(self.node_types[label].all_properties) for label in index.labels))
                unknown = set(index.properties) - declared
                if unknown:
                    raise ValueError(f"Index '{index.name}' uses undeclared properties: {sorted(unknown)}")
            elif index.relationship_type not in relationship_names:
                raise ValueError(f"Index '{index.name}' targets unknown relationship '{index.relationship_type}'")
            else:
                relationship = self.relationship_types[index.relationship_type]
                unknown = set(index.properties) - set(relationship.all_properties)
                if unknown:
                    raise ValueError(f"Index '{index.name}' uses undeclared properties: {sorted(unknown)}")
        return self


def _validate_provenance_fields(
    owner: str,
    provenance: ProvenanceConfig,
    config: NodeTypeConfig | RelationshipTypeConfig,
) -> None:
    """Validate a provenance contract against its owning property declarations."""
    required = set(config.required_properties)
    optional = set(config.optional_properties)
    missing_required = set(provenance.required_fields) - required
    missing_optional = set(provenance.optional_fields) - (required | optional)
    if missing_required:
        raise ValueError(f"{owner} provenance fields must be required properties: {sorted(missing_required)}")
    if missing_optional:
        raise ValueError(f"{owner} provenance fields are undeclared: {sorted(missing_optional)}")


def normalize_id_component(value: str) -> str:
    """Normalize Turkish and general Unicode text into a stable ASCII snake-case key."""
    translation_table: dict[int, str] = {
        ord("ı"): "i",
        ord("İ"): "I",
        ord("ş"): "s",
        ord("Ş"): "S",
    }
    translated = value.translate(translation_table)
    ascii_value = unicodedata.normalize("NFKD", translated).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_")


def stable_digest(*parts: str, length: int = 24) -> str:
    """Return a stable truncated SHA-256 digest for normalized identifier inputs."""
    canonical = "|".join(part.strip() for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]


class CompanyNode(BaseModel):
    """Company graph node."""

    id: str
    name: str
    ticker: str
    legal_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    country: str | None = "Türkiye"
    website: str | None = None
    source_report_id: str | None = None
    source_chunk_id: str | None = None
    source_page: int | None = None

    @classmethod
    def create_id(cls, ticker: str) -> str:
        return f"company:{ticker.upper().strip()}"


class ReportNode(BaseModel):
    """Corporate report document node."""

    id: str
    document_id: str
    ticker: str
    year: int
    report_type: str
    language: str
    source_file: str
    sha256: str
    source_url: str | None = None
    source_domain: str | None = None
    total_pages: int | None = None
    validation_status: str | None = None

    @classmethod
    def create_id(
        cls,
        ticker: str,
        year: int,
        report_type: str = "annual_report",
        language: str = "tr",
    ) -> str:
        document_id = f"{ticker.upper().strip()}__{year}__{report_type}__{language.lower().strip()}"
        return f"report:{document_id}"


class ChunkNode(BaseModel):
    """Text chunk used as the graph's citation anchor."""

    id: str
    chunk_id: str
    report_id: str
    document_id: str
    source_file: str
    page_number: int
    chunk_index: int
    company: str | None = None
    ticker: str | None = None
    year: int | None = None
    report_type: str | None = None
    language: str | None = None
    token_count: int | None = None
    text: str | None = None

    @classmethod
    def create_id(cls, chunk_id: str) -> str:
        return f"chunk:{chunk_id.lower().strip()}"


class PersonNode(BaseModel):
    """Company-scoped person mention, avoiding unsafe cross-company identity merges."""

    id: str
    name: str
    normalized_name: str
    company_id: str
    source_report_id: str
    source_chunk_id: str
    source_page: int
    aliases: list[str] = Field(default_factory=list)

    @classmethod
    def create_id(cls, ticker: str, name: str) -> str:
        return f"person:{ticker.upper().strip()}:{normalize_id_component(name)}"


class ProductNode(BaseModel):
    """Company-scoped product, service, or brand node."""

    id: str
    name: str
    normalized_name: str
    company_id: str
    source_report_id: str
    source_chunk_id: str
    source_page: int
    category: str | None = None
    description: str | None = None
    brand: str | None = None

    @classmethod
    def create_id(cls, ticker: str, name: str) -> str:
        return f"product:{ticker.upper().strip()}:{normalize_id_component(name)}"


class SectorNode(BaseModel):
    """Normalized business sector node."""

    id: str
    name: str
    normalized_name: str
    classification_system: str | None = None
    classification_code: str | None = None
    source_report_id: str | None = None
    source_chunk_id: str | None = None
    source_page: int | None = None

    @classmethod
    def create_id(cls, sector_name: str) -> str:
        return f"sector:{normalize_id_component(sector_name)}"


class FinancialMetricNode(BaseModel):
    """A sourced financial observation, not a global metric definition."""

    id: str
    metric_key: str
    name: str
    value: float
    unit: str
    company_id: str
    date_id: str
    scope: str
    source_report_id: str
    source_chunk_id: str
    source_page: int
    reported_value: str | None = None
    scale: int | None = None
    statement: str | None = None
    notes: str | None = None
    confidence: float | None = None

    @classmethod
    def create_id(
        cls,
        ticker: str,
        metric_name: str,
        date_value: str,
        source_report_id: str,
        scope: str = "CONSOLIDATED",
    ) -> str:
        metric_key = normalize_id_component(metric_name)
        digest = stable_digest(
            f"company:{ticker.upper().strip()}",
            metric_key,
            f"date:{date_value}",
            scope.upper().strip(),
            source_report_id,
        )
        return f"metric:{ticker.upper().strip()}:{digest}"


class EventNode(BaseModel):
    """A company event grounded in a report chunk."""

    id: str
    title: str
    normalized_title: str
    event_type: str
    company_id: str
    date_id: str
    source_report_id: str
    source_chunk_id: str
    source_page: int
    description: str | None = None
    status: str | None = None
    confidence: float | None = None

    @classmethod
    def create_id(cls, ticker: str, date_value: str, title: str, source_report_id: str) -> str:
        digest = stable_digest(
            f"company:{ticker.upper().strip()}",
            f"date:{date_value}",
            normalize_id_component(title),
            source_report_id,
        )
        return f"event:{ticker.upper().strip()}:{digest}"


class DateNode(BaseModel):
    """Canonical day, month, quarter, or year node."""

    id: str
    value: str
    granularity: str
    start_date: str | None = None
    end_date: str | None = None
    fiscal_year: int | None = None
    quarter: int | None = None

    @classmethod
    def create_id(cls, value: str) -> str:
        return f"date:{value.upper().strip()}"


class TimePeriodNode(BaseModel):
    """Backward-compatible legacy model; new graph data should use :class:`DateNode`."""

    id: str
    year: int
    quarter: str | None = None

    @classmethod
    def create_id(cls, year: int) -> str:
        return f"period:{year}"


class GraphRelationship(BaseModel):
    """A directed, deterministically identified graph relationship."""

    id: str
    source_id: str
    source_label: str
    relationship_type: str
    target_id: str
    target_label: str
    properties: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create_id(
        cls,
        relationship_type: str,
        source_id: str,
        target_id: str,
        *qualifiers: str,
    ) -> str:
        rel_key = relationship_type.lower().strip()
        digest = stable_digest(relationship_type.upper().strip(), source_id, target_id, *qualifiers)
        return f"rel:{rel_key}:{digest}"
