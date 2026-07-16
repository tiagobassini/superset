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
"""Safe, multilingual helpers for analytics resource discovery."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from superset.ai.planner import AnalyticsIntent

SemanticExpander = Callable[[str, str], Iterable[str]]

MAX_DISCOVERY_TERMS = 24
MAX_SEMANTIC_TERMS = 8
MAX_SEMANTIC_TERM_LENGTH = 80
MAX_DISCOVERY_COLUMNS = 50
MAX_DISCOVERY_CANDIDATES = 20
MAX_DISCOVERY_CHOICES = 3

# Selecting a source is deliberately stricter than ranking it.  A source must
# have enough independent signals and be clearly ahead of the next one before
# the assistant can use it without asking the user.
AUTO_SELECT_MIN_SCORE = 24
AUTO_SELECT_MIN_MARGIN = 10

# This small, versioned vocabulary is intentionally local and deterministic.
# Provider-suggested terms are optional additions and never replace lexical search.
MULTILINGUAL_TERM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {"venda", "vendas", "sale", "sales", "venta", "ventas", "vente", "ventes"}
    ),
    frozenset({"receita", "revenue", "ingreso", "ingresos", "recette", "recettes"}),
    frozenset({"pedido", "pedidos", "order", "orders", "commande", "commandes"}),
    frozenset({"cliente", "clientes", "customer", "customers", "client", "clients"}),
    frozenset(
        {
            "produto",
            "produtos",
            "product",
            "products",
            "producto",
            "productos",
            "produit",
            "produits",
        }
    ),
)


@dataclass(frozen=True)
class DiscoveryQuery:
    """An in-memory, multilingual representation of an analytics topic.

    The original topic is retained for display only. Normalized and expanded
    terms are derived values used for safe resource matching; they are never
    persisted back to Superset metadata.
    """

    topic: str
    prompt_language: str
    normalized_topic: str
    lexical_terms: tuple[str, ...]
    synonyms: tuple[str, ...]
    expanded_terms: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryCandidate:
    """A permission-filtered data source ranked for an analytics request."""

    resource_type: str
    resource_id: int | None
    name: str
    database_id: int | None
    database_name: str | None
    schema: str | None
    columns: tuple[tuple[str, str], ...]
    source_key: str
    description: str = ""
    related_names: tuple[str, ...] = ()
    score: int = 0
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return only safe metadata suitable for a provider or chat client."""
        return {
            "type": self.resource_type,
            "id": self.resource_id,
            "name": self.name,
            "database_id": self.database_id,
            "database": self.database_name,
            "schema": self.schema,
            "related_sources": list(self.related_names),
            "columns": [
                {"name": name, "type": column_type}
                for name, column_type in self.columns
            ],
            "score": self.score,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DiscoveryCandidate":
        """Restore a candidate previously stored in the short-lived chat cache."""
        columns = tuple(
            (str(column.get("name", "")), str(column.get("type", "UNKNOWN")))
            for column in value.get("columns", [])
            if isinstance(column, Mapping) and column.get("name")
        )
        return cls(
            resource_type=str(value["type"]),
            resource_id=value.get("id"),
            name=str(value["name"]),
            database_id=value.get("database_id"),
            database_name=value.get("database"),
            schema=value.get("schema"),
            columns=columns,
            source_key=(
                f"cached:{value.get('type')}:{value.get('database_id')}:"
                f"{value.get('id')}:{value.get('name')}"
            ),
            related_names=tuple(str(name) for name in value.get("related_sources", [])),
            score=int(value.get("score", 0)),
            reasons=tuple(str(reason) for reason in value.get("reasons", [])),
        )


@dataclass(frozen=True)
class DiscoveryResult:
    """Safe discovery output and counts used for audit and chat progress."""

    query: DiscoveryQuery
    candidates: tuple[DiscoveryCandidate, ...]
    searched: Mapping[str, int]

    def to_dict(self, limit: int = 5) -> dict[str, Any]:
        """Return a compact, provider-safe representation of the discovery."""
        return {
            "topic": self.query.topic,
            "terms": list(self.query.expanded_terms),
            "searched": dict(self.searched),
            "candidates": [
                candidate.to_dict() for candidate in self.candidates[:limit]
            ],
        }


@dataclass(frozen=True)
class DiscoveryDecision:
    """The safe next step after ranking accessible discovery candidates."""

    selected: DiscoveryCandidate | None
    alternatives: tuple[DiscoveryCandidate, ...]
    reason: str

    @property
    def requires_user_selection(self) -> bool:
        """Whether the user must choose from concrete discovered sources."""
        return self.reason == "ambiguous"


def decide_discovery(
    result: DiscoveryResult, intent: "AnalyticsIntent | None" = None
) -> DiscoveryDecision:
    """Select only an unambiguous source, otherwise retain concrete choices.

    Database entries provide useful search context but are not executable data
    sources, so they are never selected or proposed as the final source.
    """
    candidates = tuple(
        candidate
        for candidate in result.candidates
        if candidate.resource_type in {"dataset", "table", "saved_query"}
        and candidate.score > 0
    )
    if getattr(intent, "time_grain", None) == "year":
        candidates = tuple(
            candidate
            for candidate in candidates
            if classify_columns(
                [
                    {"name": name, "type": column_type}
                    for name, column_type in candidate.columns
                ]
            )["temporal"]
        )
    if not candidates:
        return DiscoveryDecision(None, (), "no_candidates")

    best = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    is_confident = best.score >= AUTO_SELECT_MIN_SCORE
    has_clear_margin = (
        runner_up is None
        or best.score - runner_up.score >= AUTO_SELECT_MIN_MARGIN
    )
    if is_confident and has_clear_margin:
        return DiscoveryDecision(best, (), "auto_selected")
    return DiscoveryDecision(None, candidates[:MAX_DISCOVERY_CHOICES], "ambiguous")


def build_discovery_query(
    topic: str,
    prompt_language: str | None = None,
    semantic_expander: SemanticExpander | None = None,
) -> DiscoveryQuery:
    """Build a bounded query with lexical and multilingual expansion.

    A semantic expander is optional because discovery must remain available
    when the provider is unavailable, slow, or returns unsuitable terms.
    """
    normalized_topic = normalize_discovery_text(topic)
    tokens = _tokenize(normalized_topic)
    lexical_terms = _unique_terms((normalized_topic, *tokens, *_singular_forms(tokens)))
    language = prompt_language or _detect_language(lexical_terms)
    synonyms = _dictionary_synonyms(lexical_terms)
    semantic_terms = _semantic_terms(
        semantic_expander if not synonyms else None,
        normalized_topic,
        language,
    )
    expanded_terms = _unique_terms(
        (*lexical_terms, *synonyms, *semantic_terms), limit=MAX_DISCOVERY_TERMS
    )
    return DiscoveryQuery(
        topic=topic,
        prompt_language=language,
        normalized_topic=normalized_topic,
        lexical_terms=lexical_terms,
        synonyms=synonyms,
        expanded_terms=expanded_terms,
    )


def normalize_discovery_text(value: str) -> str:
    """Normalize text for matching without changing the original resource name."""
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    without_punctuation = re.sub(r"[^\w\s_-]", " ", without_accents)
    return " ".join(re.sub(r"[_-]+", " ", without_punctuation).split())


def rank_resources(
    resources: Iterable[dict[str, Any]], search: str | DiscoveryQuery
) -> list[dict[str, Any]]:
    """Return accessible resources ordered by deterministic name relevance."""
    terms = (
        search.expanded_terms
        if isinstance(search, DiscoveryQuery)
        else build_discovery_query(search).expanded_terms
    )
    return sorted(
        resources,
        key=lambda resource: (
            -_score(_resource_name(resource), terms),
            _resource_name(resource),
        ),
    )


def classify_columns(columns: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """Identify useful temporal, measure, identifier and dimension columns."""
    groups = {"temporal": [], "measures": [], "identifiers": [], "dimensions": []}
    for column in columns:
        name = str(column.get("name") or column.get("column_name") or "")
        column_type = str(column.get("type") or "").casefold()
        normalized = _normalize(name)
        if any(token in column_type for token in ("date", "time")) or any(
            token in normalized
            for token in ("date", "data", "fecha", "year", "ano", "annee")
        ):
            groups["temporal"].append(name)
        elif normalized == "id" or normalized.endswith(" id"):
            groups["identifiers"].append(name)
        elif any(
            token in column_type
            for token in ("int", "numeric", "decimal", "float", "double")
        ) or any(
            token in normalized
            for token in (
                "amount",
                "valor",
                "total",
                "revenue",
                "receita",
                "sales",
                "ventas",
                "ventes",
            )
        ):
            groups["measures"].append(name)
        else:
            groups["dimensions"].append(name)
    return groups


class AnalyticsDiscoveryService:
    """Discover and rank only data sources available to the active user."""

    def __init__(self, user: Any) -> None:
        self.user = user

    def discover(
        self,
        query: DiscoveryQuery,
        intent: "AnalyticsIntent | None" = None,
        context: Mapping[str, Any] | None = None,
    ) -> DiscoveryResult:
        """Search accessible live metadata without returning rows or raw SQL."""
        databases = self._accessible_databases()
        candidates = [
            *self._database_candidates(databases),
            *self._dataset_candidates(),
            *self._table_candidates(databases),
            *self._saved_query_candidates(),
        ]
        scored = [
            self._score_candidate(candidate, query, intent, context or {})
            for candidate in candidates
        ]
        deduplicated = self._deduplicate(scored)
        ranked = sorted(
            deduplicated, key=lambda item: (-item.score, item.name.casefold())
        )
        return DiscoveryResult(
            query=query,
            candidates=tuple(ranked[:MAX_DISCOVERY_CANDIDATES]),
            searched={
                "databases": len(databases),
                "datasets": sum(
                    candidate.resource_type == "dataset" for candidate in candidates
                ),
                "tables": sum(
                    candidate.resource_type == "table" for candidate in candidates
                ),
                "saved_queries": sum(
                    candidate.resource_type == "saved_query" for candidate in candidates
                ),
            },
        )

    def _accessible_databases(self) -> list[Any]:
        from superset.extensions import db, security_manager
        from superset.models.core import Database

        return [
            database
            for database in db.session.query(Database)
            .order_by(Database.database_name)
            .all()
            if security_manager.can_access_database(database)
        ]

    def _database_candidates(
        self, databases: Iterable[Any]
    ) -> list[DiscoveryCandidate]:
        return [
            DiscoveryCandidate(
                resource_type="database",
                resource_id=database.id,
                name=str(database.database_name),
                database_id=database.id,
                database_name=str(database.database_name),
                schema=None,
                columns=(),
                source_key=f"database:{database.id}",
            )
            for database in databases
        ]

    def _dataset_candidates(self) -> list[DiscoveryCandidate]:
        from superset.connectors.sqla.models import SqlaTable
        from superset.extensions import db, security_manager

        candidates: list[DiscoveryCandidate] = []
        for dataset in db.session.query(SqlaTable).all():
            if not security_manager.can_access_datasource(dataset):
                continue
            columns = self._columns_from_dataset(dataset)
            candidates.append(
                DiscoveryCandidate(
                    resource_type="dataset",
                    resource_id=dataset.id,
                    name=str(dataset.table_name),
                    database_id=dataset.database_id,
                    database_name=str(dataset.database.database_name),
                    schema=dataset.schema,
                    columns=columns,
                    source_key=self._source_key(
                        dataset.database_id,
                        dataset.schema,
                        dataset.catalog,
                        dataset.table_name,
                    ),
                    description=str(getattr(dataset, "description", "") or ""),
                )
            )
        return candidates

    def _table_candidates(self, databases: Iterable[Any]) -> list[DiscoveryCandidate]:
        """Read table names and schemas only after database authorization."""
        candidates: list[DiscoveryCandidate] = []
        for database in databases:
            schema = database.get_default_schema(None)
            if not schema:
                continue
            try:
                tables = database.get_all_table_names_in_schema(
                    catalog=None, schema=schema
                )
            except Exception:  # pylint: disable=broad-except
                logger.info(
                    "Skipping inaccessible table metadata for database %s", database.id
                )
                continue
            for table_name, table_schema, catalog in tables:
                columns = self._columns_from_table(
                    database, table_name, table_schema, catalog
                )
                candidates.append(
                    DiscoveryCandidate(
                        resource_type="table",
                        resource_id=None,
                        name=str(table_name),
                        database_id=database.id,
                        database_name=str(database.database_name),
                        schema=table_schema,
                        columns=columns,
                        source_key=self._source_key(
                            database.id, table_schema, catalog, table_name
                        ),
                    )
                )
        return candidates

    def _saved_query_candidates(self) -> list[DiscoveryCandidate]:
        from superset.extensions import db, security_manager
        from superset.models.sql_lab import SavedQuery

        candidates: list[DiscoveryCandidate] = []
        for saved_query in db.session.query(SavedQuery).all():
            if saved_query.user_id != self.user.id or saved_query.database is None:
                continue
            if not security_manager.can_access_database(saved_query.database):
                continue
            aliases, tables = self._saved_query_metadata(saved_query.sql or "")
            columns = tuple((alias, "UNKNOWN") for alias in aliases)
            candidates.append(
                DiscoveryCandidate(
                    resource_type="saved_query",
                    resource_id=saved_query.id,
                    name=str(saved_query.label),
                    database_id=saved_query.db_id,
                    database_name=str(saved_query.database.database_name),
                    schema=saved_query.schema,
                    columns=columns,
                    source_key=(
                        f"saved_query:{saved_query.id}:" + ",".join(sorted(tables))
                    ),
                    description=str(getattr(saved_query, "description", "") or ""),
                    related_names=tables,
                )
            )
        return candidates

    def _score_candidate(
        self,
        candidate: DiscoveryCandidate,
        query: DiscoveryQuery,
        intent: "AnalyticsIntent | None",
        context: Mapping[str, Any],
    ) -> DiscoveryCandidate:
        """Rank name, schema and intent compatibility with explainable signals."""
        reasons: list[str] = []
        score = self._text_score(candidate.name, query.expanded_terms)
        if score:
            reasons.append("nome relacionado ao tema")
        description_score = self._text_score(
            candidate.description, query.expanded_terms
        )
        if description_score:
            score += min(8, description_score)
            reasons.append("descrição relacionada ao tema")
        related_matches = [
            name
            for name in candidate.related_names
            if self._text_score(name, query.expanded_terms)
        ]
        if related_matches:
            score += min(12, len(related_matches) * 6)
            reasons.append(
                f"fontes da consulta relacionadas: {', '.join(related_matches[:3])}"
            )
        column_matches = [
            name
            for name, _ in candidate.columns
            if self._text_score(name, query.expanded_terms)
        ]
        if column_matches:
            score += min(18, len(column_matches) * 6)
            reasons.append(f"colunas relacionadas: {', '.join(column_matches[:3])}")
        groups = classify_columns(
            [
                {"name": name, "type": column_type}
                for name, column_type in candidate.columns
            ]
        )
        if getattr(intent, "time_grain", None) == "year" and groups["temporal"]:
            score += 12
            reasons.append(f"coluna temporal: {groups['temporal'][0]}")
        if getattr(intent, "metric", None) == "count" and groups["identifiers"]:
            score += 8
            reasons.append(f"identificador para contagem: {groups['identifiers'][0]}")
        elif groups["measures"]:
            score += 6
            reasons.append(f"medida disponível: {groups['measures'][0]}")
        resource_name = str(context.get("resource_name") or "")
        if resource_name and normalize_discovery_text(
            resource_name
        ) == normalize_discovery_text(candidate.name):
            score += 10
            reasons.append("fonte no contexto atual")
        return replace(candidate, score=score, reasons=tuple(reasons))

    @staticmethod
    def _deduplicate(
        candidates: Iterable[DiscoveryCandidate],
    ) -> list[DiscoveryCandidate]:
        priority = {"dataset": 3, "saved_query": 2, "table": 1, "database": 0}
        selected: dict[str, DiscoveryCandidate] = {}
        for candidate in candidates:
            existing = selected.get(candidate.source_key)
            if existing is None or (
                candidate.score,
                priority[candidate.resource_type],
            ) > (existing.score, priority[existing.resource_type]):
                selected[candidate.source_key] = candidate
        return list(selected.values())

    @staticmethod
    def _source_key(
        database_id: int, schema: str | None, catalog: str | None, name: str
    ) -> str:
        return ":".join(
            ("source", str(database_id), str(catalog or ""), str(schema or ""), name)
        )

    @staticmethod
    def _columns_from_dataset(dataset: Any) -> tuple[tuple[str, str], ...]:
        return tuple(
            (str(column.column_name), str(column.type or "UNKNOWN"))
            for column in dataset.columns[:MAX_DISCOVERY_COLUMNS]
        )

    @staticmethod
    def _columns_from_table(
        database: Any,
        table_name: str,
        schema: str,
        catalog: str | None,
    ) -> tuple[tuple[str, str], ...]:
        from superset.sql.parse import Table

        try:
            columns = database.get_columns(Table(table_name, schema, catalog))
        except Exception:  # pylint: disable=broad-except
            return ()
        return tuple(
            (
                str(getattr(column, "column_name", None) or column.get("name", "")),
                str(getattr(column, "type", None) or column.get("type", "UNKNOWN")),
            )
            for column in columns[:MAX_DISCOVERY_COLUMNS]
        )

    @staticmethod
    def _saved_query_metadata(sql: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Extract aliases and source table labels without exposing SQL text."""
        aliases = re.findall(r"\bAS\s+([A-Za-z_][\w$]*)", sql, flags=re.IGNORECASE)
        tables = re.findall(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.$]*)", sql, flags=re.IGNORECASE
        )
        return _unique_names(aliases), _unique_names(tables)

    @staticmethod
    def _text_score(value: str, terms: Iterable[str]) -> int:
        normalized = normalize_discovery_text(value)
        return sum(
            10 if term == normalized else 4 if term in normalized else 0
            for term in terms
        )


def _resource_name(resource: dict[str, Any]) -> str:
    return _normalize(str(resource.get("name") or resource.get("title") or ""))


def _score(name: str, terms: tuple[str, ...]) -> int:
    if not terms:
        return 0
    return sum(4 if term == name else 2 if term in name else 0 for term in terms)


def _terms(value: str) -> tuple[str, ...]:
    return _tokenize(normalize_discovery_text(value))


def _normalize(value: str) -> str:
    return normalize_discovery_text(value)


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(term for term in re.split(r"\W+", value) if len(term) > 1)


def _singular_forms(terms: Iterable[str]) -> tuple[str, ...]:
    """Add conservative singular variants without modifying stored metadata."""
    singulars: list[str] = []
    for term in terms:
        if len(term) > 3 and term.endswith("s"):
            singulars.append(term[:-1])
    return tuple(singulars)


def _unique_terms(
    values: Iterable[str], limit: int = MAX_DISCOVERY_TERMS
) -> tuple[str, ...]:
    """Return stable, normalized unique terms subject to a strict bound."""
    terms: list[str] = []
    for value in values:
        normalized = normalize_discovery_text(value)
        if normalized and normalized not in terms:
            terms.append(normalized)
        if len(terms) == limit:
            break
    return tuple(terms)


def _unique_names(values: Iterable[str]) -> tuple[str, ...]:
    """Deduplicate identifiers while preserving their original display value."""
    names: list[str] = []
    normalized_names: set[str] = set()
    for value in values:
        normalized = normalize_discovery_text(value)
        if normalized and normalized not in normalized_names:
            names.append(value)
            normalized_names.add(normalized)
    return tuple(names)


def _dictionary_synonyms(terms: Iterable[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    term_set = set(terms)
    for group in MULTILINGUAL_TERM_GROUPS:
        if term_set.intersection(group):
            expanded.extend(sorted(group))
    return _unique_terms(expanded)


def _semantic_terms(
    semantic_expander: SemanticExpander | None,
    topic: str,
    language: str,
) -> tuple[str, ...]:
    """Use optional provider expansion while keeping lexical fallback reliable."""
    if semantic_expander is None or not topic:
        return ()
    try:
        candidates = semantic_expander(topic, language)
    except Exception:  # pylint: disable=broad-except
        return ()
    return _unique_terms(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, str) and len(candidate) <= MAX_SEMANTIC_TERM_LENGTH
        ),
        limit=MAX_SEMANTIC_TERMS,
    )


def _detect_language(terms: Iterable[str]) -> str:
    term_set = set(terms)
    language_markers = {
        "pt-BR": {
            "venda",
            "vendas",
            "receita",
            "pedido",
            "pedidos",
            "cliente",
            "clientes",
            "produto",
            "produtos",
        },
        "en-US": {
            "sale",
            "sales",
            "revenue",
            "order",
            "orders",
            "customer",
            "customers",
            "product",
            "products",
        },
        "es-ES": {
            "venta",
            "ventas",
            "ingreso",
            "ingresos",
            "pedido",
            "pedidos",
            "cliente",
            "clientes",
            "producto",
            "productos",
        },
        "fr-FR": {
            "vente",
            "ventes",
            "recette",
            "recettes",
            "commande",
            "commandes",
            "client",
            "clients",
            "produit",
            "produits",
        },
    }
    return max(
        language_markers,
        key=lambda language: len(term_set.intersection(language_markers[language])),
        default="pt-BR",
    )
