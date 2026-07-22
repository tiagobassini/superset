# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Administrator-managed semantic associations for AI source discovery."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from flask import current_app, has_app_context
from sqlalchemy.exc import OperationalError

from superset.extensions import db

if TYPE_CHECKING:
    from superset.ai.discovery import DiscoveryCandidate, DiscoveryQuery
    from superset.ai.planner import AnalyticsIntent

PRIORITY_BOOSTS = {
    "low": 8,
    "normal": 14,
    "high": 22,
}
MAX_SEMANTIC_ASSOCIATION_BOOST = 36


@dataclass(frozen=True)
class SemanticAssociation:
    """Approved mapping between business vocabulary and physical metadata."""

    name: str
    terms: tuple[str, ...]
    source_name: str
    database_name: str | None = None
    schema: str | None = None
    metric_name: str | None = None
    dimension_mappings: Mapping[str, str] | None = None
    priority: str = "normal"


@dataclass(frozen=True)
class SemanticBoost:
    """Explainable score contribution from an association."""

    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SemanticAssociationSuggestion:
    """Suggested association derived from available source metadata."""

    terms: tuple[str, ...]
    source_name: str
    database_name: str | None
    schema: str | None
    metric_name: str | None
    dimension_mappings: Mapping[str, str]
    confidence: float
    reasons: tuple[str, ...]


class SemanticAssociationCatalog:
    """Load and apply admin-approved source associations.

    Associations are advisory. They boost ranking only after the requested
    vocabulary matches and the live candidate still matches the configured
    source metadata.
    """

    def __init__(
        self,
        associations: Iterable[SemanticAssociation] | None = None,
    ) -> None:
        self._associations = tuple(associations) if associations is not None else None
        self._loaded_associations: tuple[SemanticAssociation, ...] | None = None

    def associations(self) -> tuple[SemanticAssociation, ...]:
        """Return config and database associations, tolerating pending migrations."""
        if self._associations is not None:
            return self._associations
        if self._loaded_associations is not None:
            return self._loaded_associations
        configured = self._configured_associations()
        self._loaded_associations = (*configured, *self._database_associations())
        return self._loaded_associations

    def boost(
        self,
        candidate: DiscoveryCandidate,
        query: DiscoveryQuery,
        intent: AnalyticsIntent | None,
    ) -> SemanticBoost:
        """Return the strongest valid association boost for a candidate."""
        boosts = [
            self._boost_for_association(association, candidate, query, intent)
            for association in self.associations()
        ]
        boosts = [boost for boost in boosts if boost.score > 0]
        if not boosts:
            return SemanticBoost(0, ())
        return max(boosts, key=lambda item: item.score)

    def suggest(
        self,
        candidates: Iterable[DiscoveryCandidate],
    ) -> tuple[SemanticAssociationSuggestion, ...]:
        """Infer reviewable associations from source names and columns."""
        suggestions: list[SemanticAssociationSuggestion] = []
        for candidate in candidates:
            column_names = [name for name, _ in candidate.columns]
            metric_name = _first_matching_column(
                column_names,
                ("revenue", "receita", "amount", "valor", "sales", "profit"),
            )
            product_column = _first_matching_column(
                column_names,
                ("product_name", "product_category", "product", "produto", "sku"),
            )
            customer_column = _first_matching_column(
                column_names,
                ("customer", "cliente", "client"),
            )
            terms = _suggested_terms(candidate.name, column_names)
            if not terms:
                continue
            dimensions = {}
            if product_column:
                dimensions["product"] = product_column
            if customer_column:
                dimensions["customer"] = customer_column
            confidence = min(
                0.95,
                0.35
                + (0.25 if metric_name else 0)
                + (0.15 if dimensions else 0)
                + min(0.20, len(terms) * 0.04),
            )
            suggestions.append(
                SemanticAssociationSuggestion(
                    terms=terms,
                    source_name=candidate.name,
                    database_name=candidate.database_name,
                    schema=candidate.schema,
                    metric_name=metric_name,
                    dimension_mappings=dimensions,
                    confidence=round(confidence, 2),
                    reasons=(
                        "nome e colunas indicam vocabulário de negócio",
                        "revisão administrativa recomendada",
                    ),
                )
            )
        return tuple(
            sorted(
                suggestions,
                key=lambda item: (-item.confidence, item.source_name.casefold()),
            )
        )

    def _boost_for_association(
        self,
        association: SemanticAssociation,
        candidate: DiscoveryCandidate,
        query: DiscoveryQuery,
        intent: AnalyticsIntent | None,
    ) -> SemanticBoost:
        from superset.ai.discovery import normalize_discovery_text

        query_terms = {normalize_discovery_text(term) for term in query.expanded_terms}
        association_terms = {
            normalize_discovery_text(term) for term in association.terms if term
        }
        if not query_terms.intersection(association_terms):
            return SemanticBoost(0, ())
        if normalize_discovery_text(association.source_name) != normalize_discovery_text(
            candidate.name
        ):
            return SemanticBoost(0, ())
        if association.database_name and normalize_discovery_text(
            association.database_name
        ) != normalize_discovery_text(candidate.database_name or ""):
            return SemanticBoost(0, ())
        if association.schema and normalize_discovery_text(
            association.schema
        ) != normalize_discovery_text(candidate.schema or ""):
            return SemanticBoost(0, ())

        reasons = [f"associação semântica aprovada: {association.name}"]
        score = PRIORITY_BOOSTS.get(association.priority, PRIORITY_BOOSTS["normal"])
        if association.metric_name:
            if _has_column(candidate, association.metric_name):
                score += 8
                reasons.append(f"medida associada disponível: {association.metric_name}")
            else:
                return SemanticBoost(0, ())
        requested_dimension = str(getattr(intent, "dimension", "") or "")
        mapped_dimension = (association.dimension_mappings or {}).get(
            requested_dimension
        )
        if mapped_dimension:
            if _has_column(candidate, mapped_dimension):
                score += 6
                reasons.append(f"dimensão associada disponível: {mapped_dimension}")
            else:
                return SemanticBoost(0, ())
        return SemanticBoost(
            min(MAX_SEMANTIC_ASSOCIATION_BOOST, score), tuple(reasons)
        )

    @staticmethod
    def _configured_associations() -> tuple[SemanticAssociation, ...]:
        if not has_app_context():
            return ()
        values = current_app.config.get("AI_SEMANTIC_ASSOCIATIONS", ())
        return tuple(
            association
            for value in values
            if (association := _association_from_mapping(value)) is not None
        )

    @staticmethod
    def _database_associations() -> tuple[SemanticAssociation, ...]:
        try:
            from superset.ai.models import AISemanticAssociation

            rows = (
                db.session.query(AISemanticAssociation)
                .filter(AISemanticAssociation.is_active.is_(True))
                .all()
            )
        except (OperationalError, AttributeError):
            rollback = getattr(db.session, "rollback", None)
            if rollback is not None:
                rollback()
            return ()
        return tuple(
            SemanticAssociation(
                name=str(row.name),
                terms=tuple(str(term) for term in row.terms or [] if term),
                source_name=str(row.source_name),
                database_name=row.database_name,
                schema=row.schema,
                metric_name=row.metric_name,
                dimension_mappings=dict(row.dimension_mappings or {}),
                priority=str(row.priority or "normal"),
            )
            for row in rows
        )


def _association_from_mapping(value: Any) -> SemanticAssociation | None:
    if not isinstance(value, Mapping):
        return None
    terms = tuple(str(term) for term in value.get("terms", ()) if term)
    source_name = str(value.get("source_name") or value.get("source") or "")
    if not terms or not source_name:
        return None
    return SemanticAssociation(
        name=str(value.get("name") or source_name),
        terms=terms,
        source_name=source_name,
        database_name=value.get("database_name"),
        schema=value.get("schema"),
        metric_name=value.get("metric_name") or value.get("metric"),
        dimension_mappings=dict(value.get("dimension_mappings") or {}),
        priority=str(value.get("priority") or "normal"),
    )


def _has_column(candidate: DiscoveryCandidate, column_name: str) -> bool:
    from superset.ai.discovery import normalize_discovery_text

    normalized_column = normalize_discovery_text(column_name)
    return any(
        normalize_discovery_text(name) == normalized_column
        for name, _ in candidate.columns
    )


def _first_matching_column(
    column_names: Iterable[str],
    terms: tuple[str, ...],
) -> str | None:
    from superset.ai.discovery import normalize_discovery_text

    for name in column_names:
        normalized = normalize_discovery_text(name)
        if any(normalize_discovery_text(term) in normalized for term in terms):
            return name
    return None


def _suggested_terms(
    source_name: str,
    column_names: Iterable[str],
) -> tuple[str, ...]:
    from superset.ai.discovery import infer_metadata_topics

    topics = infer_metadata_topics((source_name, *column_names))
    return tuple(topic for topic in topics if len(topic) > 2)[:8]
