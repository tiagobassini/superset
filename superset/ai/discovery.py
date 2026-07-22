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
import time
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
PRIORITY_DISCOVERY_COLUMNS = frozenset(
    {
        "sp_pop_totl",
        "sp_dyn_le00_in",
        "sh_dyn_mort",
    }
)

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
    frozenset(
        {"lucro", "profit", "beneficio", "margem", "margin", "margen", "marge"}
    ),
    frozenset({"quantidade", "quantity", "cantidad", "quantite"}),
    frozenset({"custo", "cost", "coste", "cout"}),
    frozenset({"jogo", "jogos", "game", "games", "videogame", "videogames"}),
    frozenset(
        {"voo", "voos", "flight", "flights", "vol", "vols", "vuelo", "vuelos"}
    ),
    frozenset({"atraso", "atrasos", "delay", "delays", "retard", "retards"}),
    frozenset(
        {
            "nascimento",
            "nascimentos",
            "birth",
            "births",
            "nome",
            "nomes",
            "name",
            "names",
        }
    ),
    frozenset({"populacao", "population", "poblacion"}),
    frozenset({"saude", "health", "salud", "sante"}),
    frozenset({"mortalidade", "mortality", "mortalidad", "mortalite"}),
    frozenset({"mensagem", "mensagens", "message", "messages", "chat", "chats"}),
    frozenset({"usuario", "usuarios", "user", "users"}),
)

METRIC_TERM_GROUPS: Mapping[str, tuple[str, ...]] = {
    "revenue": ("revenue", "receita", "faturamento"),
    "profit": ("profit", "lucro", "beneficio", "margin"),
    "revenue_profit": (
        "revenue",
        "receita",
        "faturamento",
        "profit",
        "lucro",
        "cost",
        "custo",
    ),
    "count": ("id", "number", "numero", "flight number", "flight_number"),
    "quantity_ordered": ("quantity ordered", "quantity_ordered"),
    "quantity": ("quantity", "quantidade", "quantity ordered", "quantity_ordered"),
    "cost": ("cost", "custo"),
    "sales": ("sales", "sale", "vendas", "ventas", "ventes"),
    "global_sales": ("global sales", "global_sales"),
    "regional_sales": ("na sales", "na_sales", "eu sales", "eu_sales"),
    "na_sales": ("na sales", "na_sales", "north america"),
    "eu_sales": ("eu sales", "eu_sales", "europe"),
    "delay": ("delay", "delays", "atraso", "atrasos"),
    "cancellations": (
        "cancelled",
        "cancellations",
        "cancelamento",
        "cancelamentos",
        "cancelado",
        "cancelados",
    ),
    "distance": ("distance", "distancia"),
    "births": ("births", "nascimentos", "num"),
    "population": ("population", "populacao", "sp pop totl", "sp_pop_totl"),
    "life_expectancy": ("life expectancy", "expectativa de vida", "sp dyn le00 in"),
    "mortality": ("mortality", "mortalidade", "sh dyn mort"),
}

DIMENSION_TERM_GROUPS: Mapping[str, tuple[str, ...]] = {
    "country": ("country", "country name", "country_name", "pais", "país"),
    "region": ("region", "regiao", "região"),
    "territory": ("territory", "territorio", "território"),
    "product_category": (
        "product category",
        "product_category",
        "category",
        "categoria",
    ),
    "product_line": ("product line", "product_line"),
    "genre": ("genre", "genero", "gênero"),
    "platform": ("platform", "plataforma"),
    "publisher": ("publisher", "publicadora"),
    "AIRLINE": ("airline", "companhia aerea", "companhia aérea"),
    "ORIGIN_AIRPORT": (
        "origin airport",
        "origin_airport",
        "aeroporto de origem",
        "aeroportos de origem",
    ),
    "name": ("name", "nome", "nomes"),
    "state": ("state", "estado"),
    "gender": ("gender", "sexo"),
}

INTENT_PROFILE_TERMS: Mapping[str, tuple[str, ...]] = {
    "sales_transactional": (
        "sales",
        "sale",
        "vendas",
        "ventas",
        "ventes",
        "revenue",
        "profit",
        "order",
        "orders",
        "transaction",
        "transactions",
        "customer",
        "product",
        "country",
        "region",
        "quantity",
    ),
    "games": (
        "game",
        "games",
        "videogame",
        "video game",
        "platform",
        "publisher",
        "genre",
        "global sales",
        "na sales",
        "eu sales",
        "jp sales",
    ),
    "flights": (
        "flight",
        "flights",
        "voo",
        "voos",
        "airline",
        "airport",
        "arrival delay",
        "departure delay",
        "cancelled",
        "distance",
    ),
    "births": (
        "birth",
        "births",
        "nascimento",
        "nascimentos",
        "name",
        "names",
        "gender",
        "state",
        "num",
    ),
    "health": (
        "health",
        "saude",
        "population",
        "populacao",
        "country",
        "region",
        "mortality",
        "life expectancy",
        "sp pop totl",
        "sp dyn le00 in",
        "sh dyn mort",
    ),
    "messages": (
        "message",
        "messages",
        "mensagem",
        "mensagens",
        "chat",
        "chats",
        "user",
        "users",
        "usuario",
        "usuarios",
        "channel",
        "thread",
        "timestamp",
        "ts",
    ),
}


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
    catalog_stats: Mapping[str, int] | None = None
    latency_ms: int = 0

    def to_dict(self, limit: int = 5) -> dict[str, Any]:
        """Return a compact, provider-safe representation of the discovery."""
        return {
            "topic": self.query.topic,
            "terms": list(self.query.expanded_terms),
            "searched": dict(self.searched),
            "catalog": dict(self.catalog_stats or {}),
            "latency_ms": self.latency_ms,
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
        runner_up is None or best.score - runner_up.score >= AUTO_SELECT_MIN_MARGIN
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
            for token in (
                "date",
                "data",
                "fecha",
                "year",
                "ano",
                "annee",
                "period",
                "month",
                "mes",
            )
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


def infer_metadata_topics(values: Iterable[str]) -> tuple[str, ...]:
    """Infer ranking signals from safe metadata without a closed topic registry."""
    normalized_values = tuple(normalize_discovery_text(value) for value in values)
    tokens = _unique_terms(
        token for value in normalized_values for token in _tokenize(value)
    )
    inferred: list[str] = list(tokens)
    for group in MULTILINGUAL_TERM_GROUPS:
        if any(term in tokens for term in group):
            inferred.extend(sorted(group))
    return _unique_terms(inferred)


class AnalyticsDiscoveryService:
    """Discover and rank only data sources available to the active user."""

    def __init__(self, user: Any, catalog: Any | None = None) -> None:
        self.user = user
        if catalog is None:
            from superset.ai.metadata_catalog import MetadataCatalogService

            catalog = MetadataCatalogService()
        self.catalog = catalog
        self._catalog_stats = {
            "hits": 0,
            "misses": 0,
            "live_schema_reads": 0,
            "live_schema_reads_avoided": 0,
        }

    def discover(
        self,
        query: DiscoveryQuery,
        intent: "AnalyticsIntent | None" = None,
        context: Mapping[str, Any] | None = None,
    ) -> DiscoveryResult:
        """Search accessible live metadata without returning rows or raw SQL."""
        started = time.monotonic()
        self._catalog_stats = {
            "hits": 0,
            "misses": 0,
            "live_schema_reads": 0,
            "live_schema_reads_avoided": 0,
        }
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
        result = DiscoveryResult(
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
            catalog_stats=dict(self._catalog_stats),
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
        # The index is populated only from the authorized live result. A
        # persistence failure leaves the request on the live-discovery path.
        self.catalog.upsert_many(deduplicated)
        return result

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

    def revalidate_candidate(
        self, candidate: DiscoveryCandidate
    ) -> DiscoveryCandidate | None:
        """Re-read the selected source before a plan can cause any write.

        Catalog metadata is useful during broad ranking only. This method is
        deliberately live and permission-filtered so a stale entry cannot
        become the schema used to build an execution plan.
        """
        try:
            if candidate.resource_type == "dataset":
                from superset.connectors.sqla.models import SqlaTable
                from superset.extensions import db, security_manager

                dataset = db.session.get(SqlaTable, candidate.resource_id)
                if dataset is None or not security_manager.can_access_datasource(
                    dataset
                ):
                    return None
                return replace(
                    candidate,
                    name=str(dataset.table_name),
                    database_id=dataset.database_id,
                    database_name=str(dataset.database.database_name),
                    schema=dataset.schema,
                    columns=self._columns_from_dataset(dataset),
                    description=str(getattr(dataset, "description", "") or ""),
                )
            if candidate.resource_type == "saved_query":
                from superset.extensions import db, security_manager
                from superset.models.sql_lab import SavedQuery

                saved_query = db.session.get(SavedQuery, candidate.resource_id)
                if (
                    saved_query is None
                    or saved_query.user_id != self.user.id
                    or saved_query.database is None
                    or not security_manager.can_access_database(saved_query.database)
                ):
                    return None
                aliases, tables = self._saved_query_metadata(saved_query.sql or "")
                return replace(
                    candidate,
                    name=str(saved_query.label),
                    database_id=saved_query.db_id,
                    database_name=str(saved_query.database.database_name),
                    schema=saved_query.schema,
                columns=self._columns_from_saved_query_aliases(aliases),
                related_names=tables,
                description=str(getattr(saved_query, "description", "") or ""),
            )
            if candidate.resource_type == "table":
                databases = {
                    database.id: database for database in self._accessible_databases()
                }
                database = databases.get(candidate.database_id)
                if database is None or candidate.schema is None:
                    return None
                from superset.sql.parse import Table

                columns = database.get_columns(
                    Table(candidate.name, candidate.schema, None)
                )
                return replace(
                    candidate,
                    database_name=str(database.database_name),
                    columns=tuple(
                        (
                            str(
                                getattr(column, "column_name", None)
                                or column.get("name", "")
                            ),
                            str(
                                getattr(column, "type", None)
                                or column.get("type", "UNKNOWN")
                            ),
                        )
                        for column in columns[:MAX_DISCOVERY_COLUMNS]
                    ),
                )
        except Exception:  # pylint: disable=broad-except
            logger.info(
                "Unable to revalidate discovery source %s", candidate.source_key
            )
            return None
        return None

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
                source_key = self._source_key(
                    database.id, table_schema, catalog, table_name
                )
                cached_candidate = self.catalog.get_fresh_candidate(source_key)
                if cached_candidate is not None and self._matches_live_table_identity(
                    cached_candidate, database, table_name, table_schema
                ):
                    self._catalog_stats["hits"] += 1
                    self._catalog_stats["live_schema_reads_avoided"] += 1
                    candidates.append(cached_candidate)
                    continue
                self._catalog_stats["misses"] += 1
                self._catalog_stats["live_schema_reads"] += 1
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
                        source_key=source_key,
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
            columns = self._columns_from_saved_query_aliases(aliases)
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

    def _score_candidate(  # noqa: C901
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
        requested_metric = str(getattr(intent, "metric", "") or "")
        metric_matches = self._matching_metric_columns(candidate, requested_metric)
        if metric_matches:
            score += min(18, len(metric_matches) * 9)
            reasons.append(f"medida solicitada: {metric_matches[0]}")
            if self._has_exact_column(candidate, metric_matches[0]):
                score += 8
                reasons.append(f"medida exata: {metric_matches[0]}")
        elif requested_metric == "revenue_profit":
            score -= 20
            reasons.append("sem todas as medidas solicitadas: revenue e profit")
        requested_dimension = str(getattr(intent, "dimension", "") or "")
        dimension_matches = self._matching_dimension_columns(
            candidate, requested_dimension
        )
        if dimension_matches:
            score += min(14, len(dimension_matches) * 7)
            reasons.append(f"dimensão solicitada: {dimension_matches[0]}")
            if self._has_exact_column(candidate, dimension_matches[0]):
                score += 6
                reasons.append(f"dimensão exata: {dimension_matches[0]}")
        if getattr(intent, "time_grain", None) == "year" and groups["temporal"]:
            score += 12
            reasons.append(f"coluna temporal: {groups['temporal'][0]}")
        elif getattr(intent, "time_grain", None) == "year":
            score -= 16
            reasons.append("sem coluna temporal para análise anual")
        if getattr(intent, "metric", None) == "count" and groups["identifiers"]:
            score += 8
            reasons.append(f"identificador para contagem: {groups['identifiers'][0]}")
        elif groups["measures"]:
            score += 6
            reasons.append(f"medida disponível: {groups['measures'][0]}")
        profile_score, profile_reasons = self._intent_profile_score(
            candidate, query, intent
        )
        score += profile_score
        reasons.extend(profile_reasons)
        resource_name = str(context.get("resource_name") or "")
        if resource_name and normalize_discovery_text(
            resource_name
        ) == normalize_discovery_text(candidate.name):
            score += 10
            reasons.append("fonte no contexto atual")
        return replace(candidate, score=score, reasons=tuple(reasons))

    @staticmethod
    def _matching_metric_columns(
        candidate: DiscoveryCandidate, requested_metric: str
    ) -> tuple[str, ...]:
        terms = METRIC_TERM_GROUPS.get(requested_metric, ())
        if not terms:
            return ()
        matches: list[str] = []
        for name, _ in candidate.columns:
            normalized = normalize_discovery_text(name)
            if any(normalize_discovery_text(term) in normalized for term in terms):
                matches.append(name)
        if requested_metric == "revenue_profit":
            normalized_matches = {
                normalize_discovery_text(match) for match in matches
            }
            has_revenue = any("revenue" in match for match in normalized_matches)
            has_profit = any("profit" in match for match in normalized_matches)
            if not has_revenue or not has_profit:
                return ()
        return tuple(matches)

    @staticmethod
    def _matching_dimension_columns(
        candidate: DiscoveryCandidate, requested_dimension: str
    ) -> tuple[str, ...]:
        terms = DIMENSION_TERM_GROUPS.get(requested_dimension, ())
        if not terms:
            return ()
        matches: list[str] = []
        for name, column_type in candidate.columns:
            if any(
                token in column_type.casefold()
                for token in ("int", "float", "double", "decimal", "numeric")
            ):
                continue
            normalized = normalize_discovery_text(name)
            if any(normalize_discovery_text(term) in normalized for term in terms):
                matches.append(name)
        return tuple(matches)

    @staticmethod
    def _has_exact_column(candidate: DiscoveryCandidate, column_name: str) -> bool:
        normalized_column = normalize_discovery_text(column_name)
        return any(
            normalize_discovery_text(name) == normalized_column
            for name, _ in candidate.columns
        )

    @classmethod
    def _intent_profile_score(
        cls,
        candidate: DiscoveryCandidate,
        query: DiscoveryQuery,
        intent: "AnalyticsIntent | None",
    ) -> tuple[int, list[str]]:
        profile = cls._intent_profile(query, intent)
        if profile is None:
            return 0, []
        haystack = cls._candidate_terms(candidate)
        required_matches = [
            term
            for term in INTENT_PROFILE_TERMS[profile]
            if normalize_discovery_text(term) in haystack
        ]
        if not required_matches:
            return -8, [f"estrutura pouco compatível com perfil {profile}"]
        score = min(24, len(required_matches) * 4)
        reasons = [f"estrutura compatível com perfil {profile}"]
        if profile == "sales_transactional" and cls._looks_like_games(candidate):
            score -= 18
            reasons.append(
                "sinais de jogos reduzem prioridade para vendas comerciais"
            )
        return score, reasons

    @staticmethod
    def _candidate_terms(candidate: DiscoveryCandidate) -> str:
        values = (
            candidate.name,
            candidate.description,
            *candidate.related_names,
            *(name for name, _ in candidate.columns),
        )
        return " ".join(normalize_discovery_text(value) for value in values)

    @staticmethod
    def _intent_profile(
        query: DiscoveryQuery, intent: "AnalyticsIntent | None"
    ) -> str | None:
        terms = set(query.expanded_terms)
        metric = str(getattr(intent, "metric", "") or "")
        if metric in {"global_sales", "na_sales", "eu_sales"}:
            return "games"
        if terms.intersection({"jogo", "jogos", "game", "games", "videogame"}):
            return "games"
        if terms.intersection(
            {"voo", "voos", "flight", "flights", "atraso", "delay"}
        ):
            return "flights"
        if terms.intersection(
            {"nascimento", "nascimentos", "birth", "births", "nome", "names"}
        ):
            return "births"
        if terms.intersection(
            {
                "populacao",
                "population",
                "saude",
                "health",
                "mortalidade",
                "mortality",
                "expectativa",
                "vida",
                "life",
                "expectancy",
            }
        ):
            return "health"
        if terms.intersection(
            {
                "chat",
                "chats",
                "mensagem",
                "mensagens",
                "message",
                "messages",
                "usuario",
                "usuarios",
                "user",
                "users",
            }
        ):
            return "messages"
        if terms.intersection({"venda", "vendas", "sale", "sales"}):
            return "sales_transactional"
        return None

    @staticmethod
    def _looks_like_games(candidate: DiscoveryCandidate) -> bool:
        haystack = AnalyticsDiscoveryService._candidate_terms(candidate)
        return any(
            term in haystack
            for term in ("video game", "videogame", "genre", "platform", "publisher")
        )

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
    def _matches_live_table_identity(
        candidate: DiscoveryCandidate,
        database: Any,
        table_name: str,
        table_schema: str,
    ) -> bool:
        """Reject cached metadata when the live database identity changed."""
        return (
            candidate.database_id == database.id
            and candidate.database_name == str(database.database_name)
            and candidate.schema == table_schema
            and candidate.name == str(table_name)
        )

    @staticmethod
    def _columns_from_dataset(dataset: Any) -> tuple[tuple[str, str], ...]:
        return AnalyticsDiscoveryService._prioritized_columns(
            (str(column.column_name), str(column.type or "UNKNOWN"))
            for column in dataset.columns
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
        return AnalyticsDiscoveryService._prioritized_columns(
            (
                str(getattr(column, "column_name", None) or column.get("name", "")),
                str(getattr(column, "type", None) or column.get("type", "UNKNOWN")),
            )
            for column in columns
        )

    @staticmethod
    def _prioritized_columns(
        columns: Iterable[tuple[str, str]],
    ) -> tuple[tuple[str, str], ...]:
        selected: list[tuple[str, str]] = []
        priority: list[tuple[str, str]] = []
        for index, column in enumerate(columns):
            name, _ = column
            normalized = normalize_discovery_text(name).replace(" ", "_")
            if index < MAX_DISCOVERY_COLUMNS:
                selected.append(column)
            elif normalized in PRIORITY_DISCOVERY_COLUMNS:
                priority.append(column)
        existing = {name for name, _ in selected}
        selected.extend(column for column in priority if column[0] not in existing)
        return tuple(selected)

    @staticmethod
    def _columns_from_saved_query_aliases(
        aliases: Iterable[str],
    ) -> tuple[tuple[str, str], ...]:
        columns: list[tuple[str, str]] = []
        for alias in aliases:
            normalized = normalize_discovery_text(alias)
            if normalized in {"period", "month", "year"}:
                column_type = "DATE"
            elif normalized.startswith(("sum ", "avg ", "count ", "metric")):
                column_type = "NUMERIC"
            else:
                column_type = "UNKNOWN"
            columns.append((alias, column_type))
        return tuple(columns)

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
