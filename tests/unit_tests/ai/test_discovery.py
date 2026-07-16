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
"""Tests for safe analytics discovery helpers."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from superset.ai.discovery import (
    AnalyticsDiscoveryService,
    AUTO_SELECT_MIN_MARGIN,
    build_discovery_query,
    classify_columns,
    decide_discovery,
    DiscoveryCandidate,
    DiscoveryResult,
    infer_metadata_topics,
    MAX_SEMANTIC_TERMS,
    normalize_discovery_text,
    rank_resources,
)
from superset.ai.metadata_catalog import MetadataCatalogService


def _candidate(name: str, score: int, resource_id: int = 1) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        resource_type="dataset",
        resource_id=resource_id,
        name=name,
        database_id=1,
        database_name="Examples",
        schema="public",
        columns=(("order_date", "DATE"), ("amount", "NUMERIC")),
        source_key=f"source:{resource_id}",
        score=score,
        reasons=("coluna temporal: order_date",),
    )


def test_decide_discovery_selects_only_a_confident_clear_winner() -> None:
    result = DiscoveryResult(
        build_discovery_query("vendas"),
        (_candidate("international_sales", 40), _candidate("sales_archive", 29, 2)),
        {},
    )

    decision = decide_discovery(result)

    assert decision.reason == "auto_selected"
    assert decision.selected is not None
    assert decision.selected.name == "international_sales"
    assert decision.alternatives == ()


def test_decide_discovery_requires_a_choice_for_close_or_weak_results() -> None:
    result = DiscoveryResult(
        build_discovery_query("vendas"),
        (
            _candidate("sales_current", 40),
            _candidate("sales_history", 40 - AUTO_SELECT_MIN_MARGIN + 1, 2),
            _candidate("sales_forecast", 20, 3),
            _candidate("sales_legacy", 19, 4),
        ),
        {},
    )

    decision = decide_discovery(result)

    assert decision.requires_user_selection
    assert [candidate.name for candidate in decision.alternatives] == [
        "sales_current",
        "sales_history",
        "sales_forecast",
    ]


def test_decide_discovery_reports_no_selectable_source() -> None:
    result = DiscoveryResult(
        build_discovery_query("vendas"),
        (
            DiscoveryCandidate(
                resource_type="database",
                resource_id=1,
                name="Examples",
                database_id=1,
                database_name="Examples",
                schema=None,
                columns=(),
                source_key="database:1",
                score=100,
            ),
        ),
        {},
    )

    decision = decide_discovery(result)

    assert decision.reason == "no_candidates"
    assert decision.selected is None


def test_decide_discovery_rejects_yearly_source_without_temporal_column() -> None:
    result = DiscoveryResult(
        build_discovery_query("vendas"),
        (
            DiscoveryCandidate(
                resource_type="dataset",
                resource_id=1,
                name="sales_without_dates",
                database_id=1,
                database_name="Examples",
                schema="public",
                columns=(("amount", "NUMERIC"),),
                source_key="source:1",
                score=50,
            ),
        ),
        {},
    )

    decision = decide_discovery(result, SimpleNamespace(time_grain="year"))

    assert decision.reason == "no_candidates"


def test_rank_resources_prefers_exact_and_partial_topic_matches() -> None:
    resources = [
        {"name": "inventory"},
        {"name": "international_sales"},
        {"name": "sales_summary"},
    ]

    assert [
        item["name"] for item in rank_resources(resources, "international sales")
    ] == [
        "international_sales",
        "sales_summary",
        "inventory",
    ]


def test_classify_columns_identifies_chart_candidates() -> None:
    result = classify_columns(
        [
            {"name": "order_date", "type": "DATE"},
            {"name": "sale_id", "type": "INTEGER"},
            {"name": "amount", "type": "NUMERIC"},
            {"name": "country", "type": "VARCHAR"},
        ]
    )

    assert result["temporal"] == ["order_date"]
    assert result["identifiers"] == ["sale_id"]
    assert result["measures"] == ["amount"]
    assert result["dimensions"] == ["country"]


@pytest.mark.parametrize(
    ("topic", "expected_normalized", "expected_language", "expected_term"),
    [
        ("international_sales", "international sales", "en-US", "vendas"),
        ("vendas-internacionais", "vendas internacionais", "pt-BR", "sales"),
        ("ventes_annuelles", "ventes annuelles", "fr-FR", "ventas"),
        ("ventas por año", "ventas por ano", "es-ES", "ventes"),
    ],
)
def test_build_discovery_query_normalizes_and_expands_languages(
    topic: str,
    expected_normalized: str,
    expected_language: str,
    expected_term: str,
) -> None:
    query = build_discovery_query(topic)

    assert query.topic == topic
    assert query.normalized_topic == expected_normalized
    assert query.prompt_language == expected_language
    assert expected_term in query.expanded_terms


def test_normalize_discovery_text_handles_accents_and_separators() -> None:
    assert normalize_discovery_text("  Véndas,__por-Áno!  ") == "vendas por ano"


def test_discovery_query_adds_conservative_singular_variants() -> None:
    query = build_discovery_query("faturamentos")

    assert "faturamentos" in query.lexical_terms
    assert "faturamento" in query.lexical_terms


def test_discovery_query_falls_back_to_local_terms_when_semantic_expansion_fails() -> (
    None
):
    def failing_expander(_: str, __: str) -> list[str]:
        raise RuntimeError("provider unavailable")

    query = build_discovery_query("vendas", semantic_expander=failing_expander)

    assert "sales" in query.expanded_terms
    assert set(query.expanded_terms) == set(query.lexical_terms).union(query.synonyms)


def test_discovery_query_bounds_semantic_expansion() -> None:
    def expander(_: str, __: str) -> list[str]:
        return [f"term-{index}" for index in range(MAX_SEMANTIC_TERMS + 4)]

    query = build_discovery_query("tema", semantic_expander=expander)

    assert (
        len(set(query.expanded_terms) - set(query.lexical_terms)) == MAX_SEMANTIC_TERMS
    )


def test_discovery_query_uses_semantic_expansion_for_unfamiliar_topic() -> None:
    calls: list[tuple[str, str]] = []

    def expander(topic: str, language: str) -> list[str]:
        calls.append((topic, language))
        return ["delinquency", "default"]

    query = build_discovery_query(
        "inadimplência", prompt_language="pt-BR", semantic_expander=expander
    )

    assert calls == [("inadimplencia", "pt-BR")]
    assert {"delinquency", "default"} <= set(query.expanded_terms)


def test_rank_resources_uses_multilingual_query_expansion() -> None:
    resources = [{"name": "inventory"}, {"name": "international_sales"}]

    assert (
        rank_resources(resources, build_discovery_query("ventes"))[0]["name"]
        == "international_sales"
    )


def test_discovery_service_ranks_schema_matches_and_deduplicates_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SimpleNamespace(
        id=1,
        database_name="Examples",
        get_default_schema=lambda _: "public",
        get_all_table_names_in_schema=lambda **_: {("fato_001", "public", None)},
        get_columns=lambda _: [
            SimpleNamespace(column_name="order_date", type="DATE"),
            SimpleNamespace(column_name="sale_id", type="INTEGER"),
            SimpleNamespace(column_name="amount", type="NUMERIC"),
        ],
    )
    dataset = SimpleNamespace(
        id=10,
        table_name="fato_001",
        database_id=1,
        database=database,
        schema="public",
        catalog=None,
        description="Indicadores comerciais",
        columns=[
            SimpleNamespace(column_name="order_date", type="DATE"),
            SimpleNamespace(column_name="sale_id", type="INTEGER"),
            SimpleNamespace(column_name="amount", type="NUMERIC"),
        ],
    )
    saved_query = SimpleNamespace(
        id=20,
        user_id=7,
        database=database,
        db_id=1,
        schema="public",
        label="relatorio_final",
        description="",
        sql="SELECT order_date AS year, amount AS sales FROM sales_fact",
    )

    class Query:
        def __init__(self, values: list[object]) -> None:
            self.values = values

        def order_by(self, *_: object) -> "Query":
            return self

        def all(self) -> list[object]:
            return self.values

    monkeypatch.setattr(
        "superset.extensions.db.session",
        SimpleNamespace(
            query=lambda model: Query(
                [database]
                if model.__name__ == "Database"
                else [dataset]
                if model.__name__ == "SqlaTable"
                else [saved_query]
            )
        ),
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_database", lambda _: True
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_datasource", lambda _: True
    )

    result = AnalyticsDiscoveryService(SimpleNamespace(id=7)).discover(
        build_discovery_query("ventes"),
        intent=SimpleNamespace(time_grain="year", metric="count"),
    )

    candidates = {candidate.resource_type: candidate for candidate in result.candidates}
    assert result.searched == {
        "databases": 1,
        "datasets": 1,
        "tables": 1,
        "saved_queries": 1,
    }
    assert candidates["dataset"].name == "fato_001"
    assert candidates["dataset"].score > 0
    assert "coluna temporal: order_date" in candidates["dataset"].reasons
    assert "table" not in candidates
    assert candidates["saved_query"].columns == (
        ("year", "UNKNOWN"),
        ("sales", "UNKNOWN"),
    )
    assert candidates["saved_query"].related_names == ("sales_fact",)
    assert (
        "fontes da consulta relacionadas: sales_fact"
        in candidates["saved_query"].reasons
    )
    assert "sql" not in candidates["saved_query"].to_dict()


def test_discovery_service_never_returns_inaccessible_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SimpleNamespace(id=1, database_name="Allowed")
    denied_database = SimpleNamespace(id=2, database_name="Denied")
    allowed_dataset = SimpleNamespace(
        id=10,
        table_name="sales",
        database_id=1,
        database=database,
        schema="public",
        catalog=None,
        description="",
        columns=[],
    )
    denied_dataset = SimpleNamespace(
        id=11,
        table_name="secret_sales",
        database_id=2,
        database=denied_database,
        schema="private",
        catalog=None,
        description="",
        columns=[],
    )

    class Query:
        def __init__(self, values: list[object]) -> None:
            self.values = values

        def order_by(self, *_: object) -> "Query":
            return self

        def all(self) -> list[object]:
            return self.values

    monkeypatch.setattr(
        "superset.extensions.db.session",
        SimpleNamespace(
            query=lambda model: Query(
                [database, denied_database]
                if model.__name__ == "Database"
                else [allowed_dataset, denied_dataset]
                if model.__name__ == "SqlaTable"
                else []
            )
        ),
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_database",
        lambda item: item.id == 1,
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_datasource",
        lambda item: item.id == 10,
    )
    monkeypatch.setattr(AnalyticsDiscoveryService, "_table_candidates", lambda *_: [])

    result = AnalyticsDiscoveryService(SimpleNamespace(id=7)).discover(
        build_discovery_query("sales")
    )

    assert [candidate.name for candidate in result.candidates] == ["sales", "Allowed"]


def test_saved_query_discovery_enforces_owner_and_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_database = SimpleNamespace(id=1, database_name="Allowed")
    denied_database = SimpleNamespace(id=2, database_name="Denied")
    queries = [
        SimpleNamespace(
            id=1,
            user_id=7,
            database=allowed_database,
            db_id=1,
            schema="public",
            label="mine",
            description="vendas",
            sql="SELECT amount AS sales FROM orders",
        ),
        SimpleNamespace(
            id=2,
            user_id=8,
            database=allowed_database,
            db_id=1,
            schema="public",
            label="other-user",
            description="vendas",
            sql="SELECT amount AS sales FROM orders",
        ),
        SimpleNamespace(
            id=3,
            user_id=7,
            database=denied_database,
            db_id=2,
            schema="private",
            label="denied-db",
            description="vendas",
            sql="SELECT amount AS sales FROM orders",
        ),
    ]

    class Query:
        def all(self) -> list[object]:
            return queries

    monkeypatch.setattr(
        "superset.extensions.db.session", SimpleNamespace(query=lambda _: Query())
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_database",
        lambda database: database.id == 1,
    )

    candidates = AnalyticsDiscoveryService(
        SimpleNamespace(id=7)
    )._saved_query_candidates()

    assert [candidate.name for candidate in candidates] == ["mine"]
    assert candidates[0].columns == (("sales", "UNKNOWN"),)
    assert "SELECT" not in str(candidates[0].to_dict())


def test_catalog_payload_is_safe_multilingual_and_non_authoritative() -> None:
    candidate = DiscoveryCandidate(
        resource_type="dataset",
        resource_id=9,
        name="ventes_annuelles",
        database_id=2,
        database_name="Commerce",
        schema="public",
        columns=(("année", "DATE"), ("sales_amount", "NUMERIC")),
        source_key="source:2::public:ventes_annuelles",
        description="Vendas internacionais",
        related_names=("fato_vendas",),
    )

    payload = MetadataCatalogService(ttl_seconds=60)._payload(candidate)

    assert {"sales", "vendas", "ventas", "ventes"} <= set(payload["inferred_topics"])
    assert "pt-BR" in payload["detected_languages"]
    assert "fr-FR" in payload["detected_languages"]
    assert "sql" not in payload
    assert "rows" not in payload


def test_catalog_freshness_requires_index_version_and_no_invalidation() -> None:
    now = datetime.now(timezone.utc)
    fresh = SimpleNamespace(
        indexed_at=now,
        expires_at=now + timedelta(seconds=60),
        invalidated_at=None,
    )
    stale = SimpleNamespace(
        indexed_at=now,
        expires_at=now - timedelta(seconds=1),
        invalidated_at=None,
    )
    invalidated = SimpleNamespace(
        indexed_at=now,
        expires_at=now + timedelta(seconds=60),
        invalidated_at=now,
    )

    assert MetadataCatalogService._is_fresh(fresh)
    assert not MetadataCatalogService._is_fresh(stale)
    assert not MetadataCatalogService._is_fresh(invalidated)


def test_live_table_discovery_uses_fresh_catalog_only_as_a_schema_accelerator() -> None:
    cached = DiscoveryCandidate(
        resource_type="table",
        resource_id=None,
        name="fato_001",
        database_id=1,
        database_name="Examples",
        schema="public",
        columns=(("order_date", "DATE"), ("amount", "NUMERIC")),
        source_key="source:1::public:fato_001",
    )

    class Catalog:
        def __init__(self, candidate: DiscoveryCandidate | None) -> None:
            self.candidate = candidate

        def get_fresh_candidate(self, _: str) -> DiscoveryCandidate | None:
            return self.candidate

        def upsert_many(self, _: object) -> int:
            return 0

    database = SimpleNamespace(
        id=1,
        database_name="Examples",
        get_default_schema=lambda _: "public",
        get_all_table_names_in_schema=lambda **_: {("fato_001", "public", None)},
        get_columns=lambda _: (_ for _ in ()).throw(AssertionError("must not read")),
    )

    service = AnalyticsDiscoveryService(SimpleNamespace(id=7), catalog=Catalog(cached))
    candidates = service._table_candidates([database])

    assert candidates == [cached]
    assert service._catalog_stats == {
        "hits": 1,
        "misses": 0,
        "live_schema_reads": 0,
        "live_schema_reads_avoided": 1,
    }


def test_inferred_metadata_topics_do_not_require_a_pre_registered_topic() -> None:
    topics = infer_metadata_topics(("emissoes_carbono", "reporting_period"))

    assert "emissoes" in topics
    assert "carbono" in topics
