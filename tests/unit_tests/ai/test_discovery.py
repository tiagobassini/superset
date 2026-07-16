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

import pytest

from superset.ai.discovery import (
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
