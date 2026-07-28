"""Context-aware, deterministic entity resolution and canonicalization."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from company_graphrag.graph.extraction.models import EntityExtractionRecord
from company_graphrag.graph.models import (
    CompanyNode,
    DateNode,
    EventNode,
    FinancialMetricNode,
    PersonNode,
    ProductNode,
    SectorNode,
    stable_digest,
)
from company_graphrag.graph.resolution.models import (
    AliasRecord,
    CanonicalEntityRecord,
    EntityContext,
    MatchClass,
    ResolutionDecisionRecord,
    ResolutionMetrics,
    ResolutionRunResult,
)
from company_graphrag.graph.resolution.normalizer import (
    CompanyIdentity,
    CompanyRegistry,
    build_entity_context,
    normalize_entity_name,
    normalize_words,
)


@dataclass(frozen=True)
class PreparedRecord:
    record_key: str
    record: EntityExtractionRecord
    normalized_name: str
    context: EntityContext
    company_identity: CompanyIdentity | None


@dataclass(frozen=True)
class PairOutcome:
    left_key: str
    right_key: str
    match_class: MatchClass
    name_similarity: float
    context_similarity: float
    signals: tuple[str, ...]
    conflicts: tuple[str, ...]
    rationale: str


class UnionFind:
    def __init__(self, keys: Iterable[str]) -> None:
        self.parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        parent = self.parent[key]
        if parent != key:
            self.parent[key] = self.find(parent)
        return self.parent[key]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        self.parent[high] = low


class EntityResolutionPipeline:
    """Resolve extracted mentions without merging on name similarity alone."""

    def __init__(
        self,
        output_dir: Path,
        resolution_version: str = "day20-v1",
        company_registry: CompanyRegistry | None = None,
    ) -> None:
        if not resolution_version.strip():
            raise ValueError("resolution_version must not be blank")
        self.output_dir = Path(output_dir)
        self.resolution_version = resolution_version.strip()
        self.company_registry = company_registry or CompanyRegistry()
        self.canonical_entities_path = self.output_dir / "canonical_entities.jsonl"
        self.aliases_path = self.output_dir / "aliases.jsonl"
        self.decisions_path = self.output_dir / "resolution_decisions.jsonl"
        self.metrics_path = self.output_dir / "metrics.json"

    def run(self, entities_path: Path) -> ResolutionRunResult:
        """Load Day 19 entity JSONL and resolve all valid records."""
        records: list[EntityExtractionRecord] = []
        with Path(entities_path).open(encoding="utf-8") as entity_file:
            for line_number, line in enumerate(entity_file, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(EntityExtractionRecord.model_validate_json(line))
                except ValueError as error:
                    raise ValueError(f"Invalid entity record at {entities_path}:{line_number}: {error}") from error
        return self.resolve(records)

    def resolve(self, records: Iterable[EntityExtractionRecord]) -> ResolutionRunResult:
        """Resolve an in-memory record set and atomically replace audit outputs."""
        prepared = self._prepare_records(records)
        outcomes = self._compare_candidate_pairs(prepared)

        union_find = UnionFind(prepared)
        for outcome in outcomes:
            if outcome.match_class in {MatchClass.EXACT_MATCH, MatchClass.HIGH_CONFIDENCE_MATCH}:
                union_find.union(outcome.left_key, outcome.right_key)

        clusters: dict[str, list[PreparedRecord]] = defaultdict(list)
        for key, record in prepared.items():
            clusters[union_find.find(key)].append(record)
        sorted_clusters = [sorted(cluster, key=lambda item: item.record_key) for _, cluster in sorted(clusters.items())]

        cluster_ids = self._assign_canonical_ids(sorted_clusters)
        canonical_by_record: dict[str, str] = {}
        canonical_entities: list[CanonicalEntityRecord] = []
        for cluster in sorted_clusters:
            canonical_id = cluster_ids[cluster[0].record_key]
            canonical = self._build_canonical_entity(cluster, canonical_id)
            canonical_entities.append(canonical)
            for item in cluster:
                canonical_by_record[item.record_key] = canonical_id

        decisions = self._build_decisions(outcomes, prepared, canonical_by_record)
        aliases = self._build_aliases(prepared, outcomes, canonical_by_record)
        canonical_entities.sort(key=lambda record: (record.type, record.canonical_id))
        aliases.sort(key=lambda record: record.alias_id)
        decisions.sort(key=lambda record: record.decision_id)

        ambiguous_keys = {
            key
            for outcome in outcomes
            if outcome.match_class == MatchClass.REVIEW_REQUIRED
            for key in (outcome.left_key, outcome.right_key)
        }
        pair_counts = Counter(outcome.match_class for outcome in outcomes)
        metrics = ResolutionMetrics(
            input_record_count=len(prepared),
            canonical_entity_count=len(canonical_entities),
            merged_record_count=len(prepared) - len(canonical_entities),
            ambiguous_record_count=len(ambiguous_keys),
            exact_match_pairs=pair_counts[MatchClass.EXACT_MATCH],
            high_confidence_match_pairs=pair_counts[MatchClass.HIGH_CONFIDENCE_MATCH],
            review_required_pairs=pair_counts[MatchClass.REVIEW_REQUIRED],
            different_entity_pairs=pair_counts[MatchClass.DIFFERENT_ENTITY],
            canonical_type_distribution=dict(sorted(Counter(record.type for record in canonical_entities).items())),
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_jsonl_atomic(self.canonical_entities_path, canonical_entities)
        self._write_jsonl_atomic(self.aliases_path, aliases)
        self._write_jsonl_atomic(self.decisions_path, decisions)
        self._write_json_atomic(self.metrics_path, metrics.model_dump(mode="json"))
        return ResolutionRunResult(
            metrics=metrics,
            canonical_entities=canonical_entities,
            aliases=aliases,
            decisions=decisions,
            canonical_entities_path=self.canonical_entities_path,
            aliases_path=self.aliases_path,
            decisions_path=self.decisions_path,
            metrics_path=self.metrics_path,
        )

    def _prepare_records(
        self,
        records: Iterable[EntityExtractionRecord],
    ) -> dict[str, PreparedRecord]:
        prepared: dict[str, PreparedRecord] = {}
        for record in records:
            context = build_entity_context(record)
            normalized_name = normalize_entity_name(record.type, record.canonical_name, record.properties)
            company_identity = (
                self.company_registry.resolve(
                    record.canonical_name,
                    record.properties,
                    context.report_id,
                )
                if record.type == "Company"
                else None
            )
            record_key = self._record_key(record)
            prepared.setdefault(
                record_key,
                PreparedRecord(
                    record_key=record_key,
                    record=record,
                    normalized_name=normalized_name,
                    context=context,
                    company_identity=company_identity,
                ),
            )
        return dict(sorted(prepared.items()))

    def _compare_candidate_pairs(
        self,
        prepared: dict[str, PreparedRecord],
    ) -> list[PairOutcome]:
        by_type: dict[str, list[PreparedRecord]] = defaultdict(list)
        for record in prepared.values():
            by_type[record.record.type].append(record)

        outcomes: list[PairOutcome] = []
        for records in by_type.values():
            ordered = sorted(records, key=lambda item: item.record_key)
            for left_index, left in enumerate(ordered):
                for right in ordered[left_index + 1 :]:
                    name_similarity = self._name_similarity(left.normalized_name, right.normalized_name)
                    if not self._is_candidate_pair(left, right, name_similarity):
                        continue
                    outcomes.append(self._classify_pair(left, right, name_similarity))
        return outcomes

    @staticmethod
    def _is_candidate_pair(
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> bool:
        if left.normalized_name == right.normalized_name:
            return True
        if (
            left.record.type == "Company"
            and left.company_identity
            and right.company_identity
            and left.company_identity.ticker == right.company_identity.ticker
        ):
            return True
        if left.record.type in {"Sector", "FinancialMetric"} and left.normalized_name == right.normalized_name:
            return True
        return name_similarity >= 0.55

    def _classify_pair(
        self,
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> PairOutcome:
        context_similarity, signals, conflicts = self._context_comparison(left.context, right.context)
        entity_type = left.record.type

        if entity_type == "Company":
            match_class, rationale = self._classify_company(left, right, name_similarity)
        elif entity_type == "Person":
            match_class, rationale = self._classify_person(left, right, name_similarity)
        elif entity_type == "Product":
            match_class, rationale = self._classify_product(left, right, name_similarity)
        elif entity_type == "Sector":
            match_class, rationale = self._classify_sector(left, right, name_similarity)
        elif entity_type == "FinancialMetric":
            match_class, rationale = self._classify_metric(left, right, name_similarity)
        else:
            match_class, rationale = self._classify_conservative(left, right, name_similarity)

        return PairOutcome(
            left_key=left.record_key,
            right_key=right.record_key,
            match_class=match_class,
            name_similarity=round(name_similarity, 4),
            context_similarity=round(context_similarity, 4),
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            rationale=rationale,
        )

    @staticmethod
    def _classify_company(
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> tuple[MatchClass, str]:
        if left.company_identity and right.company_identity:
            if left.company_identity.ticker == right.company_identity.ticker:
                return MatchClass.EXACT_MATCH, "Ticker/legal-name/known-alias registry resolves both to one company."
            return MatchClass.DIFFERENT_ENTITY, "Company registry resolves the mentions to different tickers."
        if left.normalized_name == right.normalized_name:
            return MatchClass.REVIEW_REQUIRED, "Name is exact but no trusted ticker or alias registry match exists."
        if name_similarity >= 0.92:
            return MatchClass.REVIEW_REQUIRED, "High company-name similarity lacks a trusted ticker/alias confirmation."
        return MatchClass.DIFFERENT_ENTITY, "No trusted company identity signal agrees."

    @staticmethod
    def _classify_person(
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> tuple[MatchClass, str]:
        if _different_non_null(left.context.company_id, right.context.company_id):
            return MatchClass.DIFFERENT_ENTITY, "Same/similar person name appears under different companies."
        if not left.context.company_id or not right.context.company_id:
            if name_similarity >= 0.78:
                return MatchClass.REVIEW_REQUIRED, "Person company scope is missing; automatic merge is unsafe."
            return MatchClass.DIFFERENT_ENTITY, "Weak name match and missing company scope."
        if left.normalized_name == right.normalized_name:
            return MatchClass.EXACT_MATCH, "Title-normalized person name and company scope are identical."
        if name_similarity >= 0.86 and left.context.report_id == right.context.report_id:
            return MatchClass.HIGH_CONFIDENCE_MATCH, "Minor name variation occurs in the same company report."
        if name_similarity >= 0.9 and left.context.year == right.context.year:
            return MatchClass.HIGH_CONFIDENCE_MATCH, "Strong name similarity agrees with company and year context."
        if name_similarity >= 0.78:
            return MatchClass.REVIEW_REQUIRED, "Plausible person-name similarity needs human confirmation."
        return MatchClass.DIFFERENT_ENTITY, "Person name similarity is below the review threshold."

    @staticmethod
    def _classify_product(
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> tuple[MatchClass, str]:
        if _different_non_null(left.context.company_id, right.context.company_id):
            return MatchClass.DIFFERENT_ENTITY, "Product mentions belong to different companies."
        left_codes = set(left.context.model_codes)
        right_codes = set(right.context.model_codes)
        if left_codes and right_codes and left_codes != right_codes:
            return MatchClass.DIFFERENT_ENTITY, "Product model-number conflict blocks a fuzzy-name merge."
        if not left.context.company_id or not right.context.company_id:
            if name_similarity >= 0.75:
                return MatchClass.REVIEW_REQUIRED, "Product company scope is missing."
            return MatchClass.DIFFERENT_ENTITY, "Weak product similarity and missing company scope."
        if left.normalized_name == right.normalized_name:
            return MatchClass.EXACT_MATCH, "Normalized product name and company scope are identical."
        if name_similarity >= 0.88 and (
            bool(left_codes & right_codes) or left.context.report_id == right.context.report_id
        ):
            return MatchClass.HIGH_CONFIDENCE_MATCH, "Product variation agrees with company and model/report context."
        if name_similarity >= 0.7:
            return MatchClass.REVIEW_REQUIRED, "Similar product wording lacks enough model evidence."
        return MatchClass.DIFFERENT_ENTITY, "Product similarity is insufficient."

    @staticmethod
    def _classify_sector(
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> tuple[MatchClass, str]:
        left_code = left.record.properties.get("classification_code")
        right_code = right.record.properties.get("classification_code")
        if left_code and right_code and left_code != right_code:
            return MatchClass.DIFFERENT_ENTITY, "Sector classification codes conflict."
        if left.normalized_name == right.normalized_name:
            return MatchClass.EXACT_MATCH, "Sector synonym normalization resolves to one canonical label."
        if name_similarity >= 0.9 and left_code and left_code == right_code:
            return MatchClass.HIGH_CONFIDENCE_MATCH, "Sector names and classification code agree."
        if name_similarity >= 0.75:
            return MatchClass.REVIEW_REQUIRED, "Sector names are similar without a shared classification code."
        return MatchClass.DIFFERENT_ENTITY, "Sector labels do not align."

    @staticmethod
    def _classify_metric(
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> tuple[MatchClass, str]:
        hard_fields = ("company_id", "date_id", "scope", "unit", "report_id")
        conflicts = [
            field
            for field in hard_fields
            if _different_non_null(getattr(left.context, field), getattr(right.context, field))
        ]
        if conflicts:
            return MatchClass.DIFFERENT_ENTITY, f"Financial observation context conflicts on {conflicts}."
        if left.normalized_name != right.normalized_name and name_similarity < 0.85:
            return MatchClass.DIFFERENT_ENTITY, "Metric synonym and name signals do not align."
        values_match = _numeric_values_match(left.context.numeric_value, right.context.numeric_value)
        if values_match is False:
            return MatchClass.REVIEW_REQUIRED, "Same metric context has conflicting numeric values."
        if left.normalized_name == right.normalized_name and values_match is True:
            return MatchClass.EXACT_MATCH, "Metric synonym, company, period, scope, source, unit, and value agree."
        if left.normalized_name == right.normalized_name:
            return MatchClass.HIGH_CONFIDENCE_MATCH, "Metric context agrees but one numeric value is unavailable."
        if name_similarity >= 0.85 and values_match is True:
            return MatchClass.HIGH_CONFIDENCE_MATCH, "Metric wording differs while observation context and value agree."
        return MatchClass.REVIEW_REQUIRED, "Metric candidate lacks enough evidence for automatic merge."

    @staticmethod
    def _classify_conservative(
        left: PreparedRecord,
        right: PreparedRecord,
        name_similarity: float,
    ) -> tuple[MatchClass, str]:
        if _different_non_null(left.context.company_id, right.context.company_id):
            return MatchClass.DIFFERENT_ENTITY, "Company context conflicts."
        if _different_non_null(left.context.date_id, right.context.date_id):
            return MatchClass.DIFFERENT_ENTITY, "Date context conflicts."
        if left.normalized_name == right.normalized_name:
            return MatchClass.EXACT_MATCH, "Canonical key is identical and no hard context conflict exists."
        if name_similarity >= 0.85:
            return MatchClass.REVIEW_REQUIRED, "Fuzzy match for this entity type is never auto-merged."
        return MatchClass.DIFFERENT_ENTITY, "Canonical keys differ."

    @staticmethod
    def _context_comparison(
        left: EntityContext,
        right: EntityContext,
    ) -> tuple[float, list[str], list[str]]:
        signals: list[str] = []
        conflicts: list[str] = []
        fields = ("company_id", "year", "report_id", "date_id", "scope", "unit")
        comparable = 0
        matches = 0
        for field in fields:
            left_value = getattr(left, field)
            right_value = getattr(right, field)
            if left_value is None or right_value is None:
                continue
            comparable += 1
            if left_value == right_value:
                matches += 1
                signals.append(f"same_{field}")
            else:
                conflicts.append(f"different_{field}")

        left_codes = set(left.model_codes)
        right_codes = set(right.model_codes)
        if left_codes and right_codes:
            comparable += 1
            if left_codes == right_codes:
                matches += 1
                signals.append("same_model_codes")
            else:
                conflicts.append("different_model_codes")

        evidence_similarity = _jaccard(set(left.evidence_tokens), set(right.evidence_tokens))
        if evidence_similarity >= 0.25:
            signals.append("evidence_context_overlap")
        base_score = matches / comparable if comparable else 0.0
        return min(1.0, 0.8 * base_score + 0.2 * evidence_similarity), signals, conflicts

    @staticmethod
    def _name_similarity(left: str, right: str) -> float:
        if left == right:
            return 1.0
        left_words = left.replace("_", " ")
        right_words = right.replace("_", " ")
        sequence = SequenceMatcher(None, left_words, right_words).ratio()
        token_score = _jaccard(set(left_words.split()), set(right_words.split()))
        return max(sequence, 0.65 * sequence + 0.35 * token_score)

    def _assign_canonical_ids(
        self,
        clusters: list[list[PreparedRecord]],
    ) -> dict[str, str]:
        proposed: list[tuple[list[PreparedRecord], str]] = [
            (cluster, self._base_canonical_id(cluster)) for cluster in clusters
        ]
        grouped: dict[str, list[list[PreparedRecord]]] = defaultdict(list)
        for cluster, canonical_id in proposed:
            grouped[canonical_id].append(cluster)

        assigned: dict[str, str] = {}
        for base_id, same_id_clusters in sorted(grouped.items()):
            ordered_clusters = sorted(
                same_id_clusters,
                key=lambda cluster: tuple(item.record_key for item in cluster),
            )
            for index, cluster in enumerate(ordered_clusters):
                canonical_id = base_id
                if len(ordered_clusters) > 1 and index > 0:
                    cluster_digest = stable_digest(
                        *(item.record_key for item in cluster),
                        length=12,
                    )
                    canonical_id = f"{base_id}:variant:{cluster_digest}"
                for item in cluster:
                    assigned[item.record_key] = canonical_id
        return assigned

    def _base_canonical_id(self, cluster: list[PreparedRecord]) -> str:
        representative = self._representative(cluster)
        entity_type = representative.record.type
        normalized_name = representative.normalized_name
        context = representative.context
        if entity_type == "Company":
            identity = next((item.company_identity for item in cluster if item.company_identity), None)
            if identity:
                return CompanyNode.create_id(identity.ticker)
        if entity_type == "Person":
            ticker = _ticker_from_company_id(context.company_id)
            if ticker:
                return PersonNode.create_id(ticker, normalized_name)
        if entity_type == "Product":
            ticker = _ticker_from_company_id(context.company_id)
            if ticker:
                return ProductNode.create_id(ticker, normalized_name)
        if entity_type == "Sector":
            return SectorNode.create_id(normalized_name)
        if entity_type == "FinancialMetric":
            ticker = _ticker_from_company_id(context.company_id)
            if ticker and context.date_id and context.report_id:
                return FinancialMetricNode.create_id(
                    ticker,
                    normalized_name,
                    context.date_id.removeprefix("date:"),
                    context.report_id,
                    context.scope or "CONSOLIDATED",
                )
        if entity_type == "Date":
            return DateNode.create_id(normalized_name)
        if entity_type == "Event":
            ticker = _ticker_from_company_id(context.company_id)
            if ticker and context.date_id and context.report_id:
                return EventNode.create_id(
                    ticker,
                    context.date_id.removeprefix("date:"),
                    normalized_name,
                    context.report_id,
                )
        if entity_type == "Report":
            return f"report:{normalized_name}"
        if entity_type == "Chunk":
            return f"chunk:{normalized_name}"
        digest = stable_digest(
            entity_type,
            normalized_name,
            context.company_id or "",
            context.date_id or "",
            context.report_id or "",
            length=24,
        )
        return f"canonical:{entity_type.lower()}:{digest}"

    def _build_canonical_entity(
        self,
        cluster: list[PreparedRecord],
        canonical_id: str,
    ) -> CanonicalEntityRecord:
        representative = self._representative(cluster)
        canonical_name = self._canonical_display_name(cluster, representative)
        properties = dict(representative.record.properties)
        properties["id"] = canonical_id
        if representative.record.type == "Company":
            identity = next((item.company_identity for item in cluster if item.company_identity), None)
            if identity:
                properties["ticker"] = identity.ticker
                properties["name"] = identity.canonical_name
                properties["aliases"] = sorted(set(identity.aliases))
        elif representative.record.type == "Person":
            properties["name"] = canonical_name
            properties["normalized_name"] = representative.normalized_name
        elif representative.record.type == "Product":
            properties["name"] = canonical_name
            properties["normalized_name"] = representative.normalized_name
        elif representative.record.type == "Sector":
            properties["name"] = canonical_name
            properties["normalized_name"] = representative.normalized_name
        elif representative.record.type == "FinancialMetric":
            properties["name"] = canonical_name
            properties["metric_key"] = representative.normalized_name

        aliases = sorted({item.record.canonical_name for item in cluster}, key=str.casefold)
        report_ids = sorted({item.context.report_id for item in cluster if item.context.report_id is not None})
        years = sorted({item.context.year for item in cluster if item.context.year is not None})
        confidence_values = [item.record.confidence for item in cluster]
        return CanonicalEntityRecord(
            canonical_id=canonical_id,
            type=representative.record.type,
            canonical_name=canonical_name,
            normalized_name=representative.normalized_name,
            properties=properties,
            aliases=aliases,
            source_entity_ids=sorted({item.record.id for item in cluster}),
            source_record_keys=sorted(item.record_key for item in cluster),
            source_chunk_ids=sorted({item.record.source_chunk_id for item in cluster}),
            report_ids=report_ids,
            years=years,
            evidence_samples=sorted({item.record.evidence_text for item in cluster})[:5],
            average_confidence=round(sum(confidence_values) / len(confidence_values), 4),
            resolution_version=self.resolution_version,
        )

    @staticmethod
    def _representative(cluster: list[PreparedRecord]) -> PreparedRecord:
        return min(
            cluster,
            key=lambda item: (
                len(normalize_words(item.record.canonical_name).split()),
                len(item.record.canonical_name),
                -item.record.confidence,
                item.record.canonical_name.casefold(),
                item.record_key,
            ),
        )

    @staticmethod
    def _canonical_display_name(
        cluster: list[PreparedRecord],
        representative: PreparedRecord,
    ) -> str:
        identity = next((item.company_identity for item in cluster if item.company_identity), None)
        if representative.record.type == "Company" and identity:
            return identity.canonical_name
        display_names = {
            "total_revenue": "Toplam Hasılat",
            "net_profit": "Net Kâr",
            "ebitda": "FAVÖK",
            "total_assets": "Toplam Aktifler",
            "savunma_sanayii": "Savunma Sanayii",
            "telekomunikasyon": "Telekomünikasyon",
            "otomotiv": "Otomotiv",
        }
        return display_names.get(representative.normalized_name, representative.record.canonical_name)

    def _build_decisions(
        self,
        outcomes: list[PairOutcome],
        prepared: dict[str, PreparedRecord],
        canonical_by_record: dict[str, str],
    ) -> list[ResolutionDecisionRecord]:
        decisions: list[ResolutionDecisionRecord] = []
        for outcome in outcomes:
            left = prepared[outcome.left_key]
            right = prepared[outcome.right_key]
            merged = canonical_by_record[outcome.left_key] == canonical_by_record[outcome.right_key]
            decision_id = "decision:" + stable_digest(
                self.resolution_version,
                outcome.left_key,
                outcome.right_key,
                outcome.match_class.value,
                length=24,
            )
            decisions.append(
                ResolutionDecisionRecord(
                    decision_id=decision_id,
                    left_record_key=outcome.left_key,
                    right_record_key=outcome.right_key,
                    left_entity_id=left.record.id,
                    right_entity_id=right.record.id,
                    left_name=left.record.canonical_name,
                    right_name=right.record.canonical_name,
                    entity_type=left.record.type,
                    match_class=outcome.match_class,
                    name_similarity=outcome.name_similarity,
                    context_similarity=outcome.context_similarity,
                    signals=list(outcome.signals),
                    conflicts=list(outcome.conflicts),
                    rationale=outcome.rationale,
                    merged=merged,
                    left_canonical_id=canonical_by_record[outcome.left_key],
                    right_canonical_id=canonical_by_record[outcome.right_key],
                    resolution_version=self.resolution_version,
                )
            )
        return decisions

    def _build_aliases(
        self,
        prepared: dict[str, PreparedRecord],
        outcomes: list[PairOutcome],
        canonical_by_record: dict[str, str],
    ) -> list[AliasRecord]:
        outcomes_by_key: dict[str, list[PairOutcome]] = defaultdict(list)
        for outcome in outcomes:
            outcomes_by_key[outcome.left_key].append(outcome)
            outcomes_by_key[outcome.right_key].append(outcome)

        cluster_sizes = Counter(canonical_by_record.values())
        aliases: list[AliasRecord] = []
        for key, item in prepared.items():
            canonical_id = canonical_by_record[key]
            related = outcomes_by_key.get(key, [])
            accepted = [
                outcome
                for outcome in related
                if outcome.match_class in {MatchClass.EXACT_MATCH, MatchClass.HIGH_CONFIDENCE_MATCH}
                and canonical_by_record[outcome.left_key] == canonical_by_record[outcome.right_key]
            ]
            reviews = [outcome for outcome in related if outcome.match_class == MatchClass.REVIEW_REQUIRED]
            if accepted:
                match_class = (
                    MatchClass.EXACT_MATCH
                    if any(outcome.match_class == MatchClass.EXACT_MATCH for outcome in accepted)
                    else MatchClass.HIGH_CONFIDENCE_MATCH
                )
                candidate_canonical_id = None
            elif reviews:
                match_class = MatchClass.REVIEW_REQUIRED
                review = max(reviews, key=lambda outcome: outcome.name_similarity)
                other_key = review.right_key if review.left_key == key else review.left_key
                candidate_canonical_id = canonical_by_record[other_key]
            else:
                match_class = MatchClass.DIFFERENT_ENTITY
                candidate_canonical_id = None

            alias_id = "alias:" + stable_digest(
                self.resolution_version,
                key,
                canonical_id,
                length=24,
            )
            aliases.append(
                AliasRecord(
                    alias_id=alias_id,
                    source_record_key=key,
                    source_entity_id=item.record.id,
                    entity_type=item.record.type,
                    alias=item.record.canonical_name,
                    normalized_alias=item.normalized_name,
                    canonical_entity_id=canonical_id,
                    candidate_canonical_id=candidate_canonical_id,
                    match_class=match_class,
                    auto_merged=cluster_sizes[canonical_id] > 1,
                    source_chunk_id=item.record.source_chunk_id,
                    source_file=item.record.source_file,
                    page_number=item.record.page_number,
                    resolution_version=self.resolution_version,
                )
            )
        return aliases

    def _record_key(self, record: EntityExtractionRecord) -> str:
        return "record:" + stable_digest(
            record.extraction_version,
            record.id,
            record.type,
            record.canonical_name,
            record.source_chunk_id,
            record.source_file,
            str(record.page_number),
            record.evidence_text,
            json.dumps(record.properties, ensure_ascii=False, sort_keys=True, default=str),
            length=24,
        )

    @staticmethod
    def _write_jsonl_atomic(path: Path, records: list[Any]) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as output_file:
            for record in records:
                output_file.write(record.model_dump_json() + "\n")
        temporary_path.replace(path)

    @staticmethod
    def _write_json_atomic(path: Path, payload: Any) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)


def _different_non_null(left: Any, right: Any) -> bool:
    return left is not None and right is not None and left != right


def _numeric_values_match(left: float | None, right: float | None) -> bool | None:
    if left is None or right is None:
        return None
    tolerance = max(1e-9, max(abs(left), abs(right)) * 1e-6)
    return abs(left - right) <= tolerance


def _ticker_from_company_id(company_id: str | None) -> str | None:
    if company_id and company_id.startswith("company:"):
        return company_id.split(":", 1)[1].upper()
    return None


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
