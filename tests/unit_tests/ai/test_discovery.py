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

from types import SimpleNamespace

import pytest

from superset.ai.discovery import (
    AnalyticsDiscoveryService,
    build_discovery_query,
    classify_columns,
    MAX_SEMANTIC_TERMS,
    normalize_discovery_text,
    rank_resources,
)


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
