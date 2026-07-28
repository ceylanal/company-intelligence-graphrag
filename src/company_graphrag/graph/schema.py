"""Graph schema loading, record validation, and Neo4j 5 DDL generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from company_graphrag.graph.models import (
    GraphSchemaConfig,
    NodeTypeConfig,
    PropertyDefinition,
    PropertyType,
    RelationshipTypeConfig,
)

DEFAULT_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


class GraphSchemaManager:
    """Load and enforce the versioned GraphRAG schema contract."""

    def __init__(self, schema_path: Path = DEFAULT_SCHEMA_PATH) -> None:
        self.schema_path = Path(schema_path)
        self.config = self._load_schema(self.schema_path)

    def _load_schema(self, path: Path) -> GraphSchemaConfig:
        """Load YAML and validate both its shape and all internal references."""
        if not path.exists():
            raise FileNotFoundError(f"Graph schema YAML file not found: {path}")

        with path.open(encoding="utf-8") as schema_file:
            raw_data = yaml.safe_load(schema_file)
        if not isinstance(raw_data, dict):
            raise ValueError(f"Graph schema root must be a mapping: {path}")
        return GraphSchemaConfig.model_validate(raw_data)

    def get_node_types(self) -> dict[str, NodeTypeConfig]:
        """Return configured node types."""
        return self.config.node_types

    def get_relationship_types(self) -> dict[str, RelationshipTypeConfig]:
        """Return configured relationship types."""
        return self.config.relationship_types

    def validate_node_dict(
        self,
        node_label: str,
        properties: dict[str, Any],
        *,
        reject_unknown: bool = True,
    ) -> list[str]:
        """Validate a node property mapping against required fields and scalar rules."""
        if node_label not in self.config.node_types:
            return [f"Unknown node label '{node_label}' not in schema."]

        node = self.config.node_types[node_label]
        return self._validate_properties(
            owner=f"Node '{node_label}'",
            required=node.required_properties,
            optional=node.optional_properties,
            properties=properties,
            reject_unknown=reject_unknown,
        )

    def validate_relationship(
        self,
        rel_type: str,
        source_label: str,
        target_label: str,
        properties: dict[str, Any] | None = None,
        *,
        reject_unknown: bool = True,
    ) -> list[str]:
        """Validate relationship endpoints and, when supplied, relationship properties."""
        if rel_type not in self.config.relationship_types:
            return [f"Unknown relationship type '{rel_type}' not in schema."]

        errors: list[str] = []
        relationship = self.config.relationship_types[rel_type]
        if source_label not in relationship.source_labels:
            expected = ", ".join(relationship.source_labels)
            errors.append(f"Relationship '{rel_type}' expected source in [{expected}], got '{source_label}'.")
        if relationship.target != target_label:
            errors.append(f"Relationship '{rel_type}' expected target '{relationship.target}', got '{target_label}'.")

        if properties is not None:
            errors.extend(
                self._validate_properties(
                    owner=f"Relationship '{rel_type}'",
                    required=relationship.required_properties,
                    optional=relationship.optional_properties,
                    properties=properties,
                    reject_unknown=reject_unknown,
                )
            )
        return errors

    def _validate_properties(
        self,
        *,
        owner: str,
        required: dict[str, PropertyDefinition],
        optional: dict[str, PropertyDefinition],
        properties: dict[str, Any],
        reject_unknown: bool,
    ) -> list[str]:
        errors: list[str] = []
        declared = {**required, **optional}

        for property_name in required:
            if property_name not in properties or properties[property_name] is None:
                errors.append(f"{owner} missing required property '{property_name}'.")

        if reject_unknown:
            for property_name in sorted(set(properties) - set(declared)):
                errors.append(f"{owner} has unknown property '{property_name}'.")

        for property_name, value in properties.items():
            definition = declared.get(property_name)
            if definition is None or value is None:
                continue
            errors.extend(self._validate_property_value(owner, property_name, value, definition))
        return errors

    @staticmethod
    def _validate_property_value(
        owner: str,
        property_name: str,
        value: Any,
        definition: PropertyDefinition,
    ) -> list[str]:
        errors: list[str] = []
        expected = definition.type
        valid_type = {
            PropertyType.STRING: isinstance(value, str),
            PropertyType.INTEGER: isinstance(value, int) and not isinstance(value, bool),
            PropertyType.FLOAT: isinstance(value, (int, float)) and not isinstance(value, bool),
            PropertyType.BOOLEAN: isinstance(value, bool),
            PropertyType.STRING_LIST: isinstance(value, list) and all(isinstance(item, str) for item in value),
        }[expected]
        if not valid_type:
            return [f"{owner} property '{property_name}' expected {expected.value}, got {type(value).__name__}."]

        if isinstance(value, str):
            if not value.strip():
                errors.append(f"{owner} property '{property_name}' must not be blank.")
            if definition.pattern and re.fullmatch(definition.pattern, value) is None:
                errors.append(f"{owner} property '{property_name}' does not match {definition.pattern!r}.")
        if definition.allowed_values is not None and value not in definition.allowed_values:
            errors.append(
                f"{owner} property '{property_name}' must be one of {definition.allowed_values}, got {value!r}."
            )
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if definition.minimum is not None and value < definition.minimum:
                errors.append(f"{owner} property '{property_name}' must be >= {definition.minimum:g}.")
            if definition.maximum is not None and value > definition.maximum:
                errors.append(f"{owner} property '{property_name}' must be <= {definition.maximum:g}.")
        return errors

    def generate_neo4j_cypher_statements(self) -> list[str]:
        """Generate the Community Edition-compatible Neo4j 5 physical plan."""
        statements: list[str] = []

        for constraint in self.config.neo4j.constraints:
            if len(constraint.properties) == 1:
                expression = f"n.{constraint.properties[0]}"
            else:
                expression = "(" + ", ".join(f"n.{name}" for name in constraint.properties) + ")"
            statements.append(
                f"CREATE CONSTRAINT {constraint.name} IF NOT EXISTS "
                f"FOR (n:{constraint.label}) REQUIRE {expression} IS UNIQUE;"
            )

        for index in self.config.neo4j.indexes:
            if index.kind == "FULLTEXT":
                labels = "|".join(index.labels)
                properties = ", ".join(f"n.{name}" for name in index.properties)
                statements.append(
                    f"CREATE FULLTEXT INDEX {index.name} IF NOT EXISTS FOR (n:{labels}) ON EACH [{properties}];"
                )
                continue

            if index.entity == "NODE":
                properties = ", ".join(f"n.{name}" for name in index.properties)
                statements.append(
                    f"CREATE INDEX {index.name} IF NOT EXISTS FOR (n:{index.labels[0]}) ON ({properties});"
                )
            else:
                properties = ", ".join(f"r.{name}" for name in index.properties)
                statements.append(
                    f"CREATE INDEX {index.name} IF NOT EXISTS "
                    f"FOR ()-[r:{index.relationship_type}]-() ON ({properties});"
                )
        return statements
