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
"""Tests for the Examples prompt suite runner's deterministic oracles."""

from datetime import datetime, timezone
from pathlib import Path

from scripts.ai.run_example_prompt_suite import (
    build_oracle,
    evaluate_result,
    load_cases,
    PromptCase,
    PromptMetrics,
    PromptResult,
    _context_for_case,
    _requires_suite_source_selection,
    _suite_source_selection,
    _summary,
)


def test_load_cases_reads_all_documented_prompts() -> None:
    cases = load_cases(Path("docs/ai-integration/example-database-ai-prompts.md"))

    assert len(cases) == 500
    assert cases[0].id == "P01"
    assert cases[-1].id == "P500"


def test_context_marker_builds_documented_page_context() -> None:
    case = PromptCase(
        id="P51",
        prompt="Neste dashboard, crie um gráfico AI_TEST_P51.",
        expected="Contexto inicial: `dashboard:CBMES`. Usa o dashboard do contexto.",
        confirm=True,
        oracle=build_oracle(
            "P51",
            "Neste dashboard, crie um gráfico AI_TEST_P51.",
            "Contexto inicial: `dashboard:CBMES`. Usa o dashboard do contexto.",
            True,
        ),
    )

    assert _context_for_case(case) == {
        "page": "dashboard",
        "resource_name": "CBMES",
        "metadata": {"dashboard_title": "CBMES"},
    }


def test_context_uses_expected_dashboard_for_confirmed_cases() -> None:
    case = PromptCase(
        id="P301",
        prompt="Crie um gráfico AI_TEST_P301 mostrando influência sobre vendas.",
        expected="Após confirmação, chart publicado no dashboard `CBMES`.",
        confirm=True,
        oracle=build_oracle(
            "P301",
            "Crie um gráfico AI_TEST_P301 mostrando influência sobre vendas.",
            "Após confirmação, chart publicado no dashboard `CBMES`.",
            True,
        ),
    )

    assert _context_for_case(case) == {
        "page": "dashboard",
        "resource_name": "CBMES",
        "metadata": {"dashboard_title": "CBMES"},
    }


def test_oracle_extracts_sources_columns_resources_and_confirmation() -> None:
    oracle = build_oracle(
        "P15",
        "Adicione ao CBMES um gráfico AI_TEST_P15 de receita por ano do international_sales.",
        "Plano cita dashboard `CBMES`; após confirmação, chart existe e está "
        "associado ao dashboard.",
        True,
    )

    assert oracle.requires_confirmation
    assert oracle.expected_dashboard == "CBMES"
    assert "AI_TEST_P15" in oracle.expected_resources
    assert "international_sales" in oracle.expected_sources
    assert "revenue" in oracle.expected_columns
    assert "sales" not in oracle.expected_columns


def test_evaluate_result_validates_structured_facts_without_exact_text() -> None:
    case = PromptCase(
        id="P11",
        prompt="Crie o chart AI_TEST_P11 de receita anual usando international_sales.",
        expected="Plano cria chart com `transaction_date` anual e soma de `revenue`.",
        confirm=True,
        oracle=build_oracle(
            "P11",
            "Crie o chart AI_TEST_P11 de receita anual usando international_sales.",
            "Plano cria chart com `transaction_date` anual e soma de `revenue`.",
            True,
        ),
    )
    snapshot = {
        "status": "completed",
        "response": "Plano concluído",
        "pending_actions": [],
        "execution_plan": {
            "source": {"name": "international_sales"},
            "actions": [
                {
                    "tool_name": "create_chart",
                    "params": {
                        "chart_spec": {
                            "chart_title": "AI_TEST_P11",
                            "time_column": "transaction_date",
                            "metric": "SUM(revenue)",
                        }
                    },
                }
            ]
        },
        "events": [{"state": "completed", "message": "ok"}],
    }
    resources = {"charts": [{"name": "AI_TEST_P11", "url": "/explore/"}]}

    passed, failures = evaluate_result(case, snapshot, resources, "executed")

    assert passed
    assert failures == []


def test_evaluate_result_reports_missing_plan_for_confirmed_case() -> None:
    case = PromptCase(
        id="P12",
        prompt="Crie o chart AI_TEST_P12 de lucro anual em barras usando international_sales.",
        expected="Após confirmação, existe chart `AI_TEST_P12` com soma de `profit` por ano.",
        confirm=True,
        oracle=build_oracle(
            "P12",
            "Crie o chart AI_TEST_P12 de lucro anual em barras usando international_sales.",
            "Após confirmação, existe chart `AI_TEST_P12` com soma de `profit` por ano.",
            True,
        ),
    )

    passed, failures = evaluate_result(
        case,
        {"status": "awaiting_user_input", "response": "Qual tabela?", "events": []},
        {},
        "missing_plan",
    )

    assert not passed
    assert "expected one confirmed execution plan" in failures


def test_evaluate_result_normalizes_dashboard_names() -> None:
    case = PromptCase(
        id="P99",
        prompt="Adicione ao CBMES um gráfico.",
        expected="Após confirmação, gráfico publicado no dashboard `CBMES`.",
        confirm=True,
        oracle=build_oracle(
            "P99",
            "Adicione ao CBMES um gráfico.",
            "Após confirmação, gráfico publicado no dashboard `CBMES`.",
            True,
        ),
    )

    passed, failures = evaluate_result(
        case,
        {
            "status": "completed",
            "response": "Plano concluído com sucesso. - [cbmes](/superset/dashboard/c-bmes/)",
            "pending_actions": [],
            "execution_plan": {"actions": [{"tool_name": "execution_plan"}]},
            "events": [],
        },
        {},
        "executed",
    )

    assert passed
    assert failures == []


def test_runner_detects_source_selection_prompt_for_confirmed_suite_case() -> None:
    snapshot = {
        "status": "awaiting_user_input",
        "response": (
            "Encontrei mais de uma fonte acessível relacionada a “vendas”:\n"
            "1. Dataset `cleaned_sales_data` — banco examples; colunas: sales.\n"
            "2. Dataset `international_sales` — banco examples; colunas: revenue.\n"
            "Qual fonte deseja utilizar? Responda com o número, nome exato ou "
            "tipo e ID?"
        ),
    }

    assert _requires_suite_source_selection(snapshot)


def test_runner_selects_suggested_source_that_matches_oracle_terms() -> None:
    case = PromptCase(
        id="P206",
        prompt="Crie um gráfico AI_TEST_P206 comparando price vs volume.",
        expected="Após confirmação, chart com `revenue` e `quantity`.",
        confirm=True,
        oracle=build_oracle(
            "P206",
            "Crie um gráfico AI_TEST_P206 comparando price vs volume.",
            "Após confirmação, chart com `revenue` e `quantity`.",
            True,
        ),
    )
    snapshot = {
        "status": "awaiting_user_input",
        "response": (
            "Encontrei mais de uma fonte acessível relacionada a “price”:\n"
            "1. Dataset `cleaned_sales_data` — banco examples; colunas: price_each, sales.\n"
            "2. Dataset `international_sales` — banco examples; colunas: revenue, quantity.\n"
            "Qual fonte deseja utilizar? Responda com o número, nome exato ou "
            "tipo e ID?"
        ),
    }

    assert _suite_source_selection(snapshot, case) == "2"


def test_runner_keeps_source_alternatives_when_case_expects_shortlist() -> None:
    case = PromptCase(
        id="P07",
        prompt="Quero analisar vendas, mas não sei qual dataset usar.",
        expected=(
            "Executa descoberta e retorna até três alternativas com metadados; "
            "não pede “qual tabela?”."
        ),
        confirm=False,
        oracle=build_oracle(
            "P07",
            "Quero analisar vendas, mas não sei qual dataset usar.",
            "Executa descoberta e retorna até três alternativas com metadados; "
            "não pede “qual tabela?”.",
            False,
        ),
    )
    snapshot = {
        "status": "awaiting_user_input",
        "response": (
            "Encontrei mais de uma fonte acessível relacionada a “vendas”:\n"
            "1. Dataset `cleaned_sales_data` — banco examples; colunas: sales.\n"
            "2. Dataset `international_sales` — banco examples; colunas: revenue.\n"
            "Qual fonte deseja utilizar? Responda com o número, nome exato ou "
            "tipo e ID?"
        ),
    }

    assert _suite_source_selection(snapshot, case) is None


def test_runner_does_not_select_source_for_generic_clarification() -> None:
    snapshot = {
        "status": "awaiting_user_input",
        "response": "Em qual dashboard o gráfico deve ser publicado?",
    }

    assert not _requires_suite_source_selection(snapshot)


def test_summary_reports_suite_duration() -> None:
    started_at = datetime(2026, 7, 22, 17, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 7, 22, 17, 0, 12, 345000, tzinfo=timezone.utc)

    summary = _summary(
        [
            PromptResult(
                id="P01",
                prompt="prompt",
                status="completed",
                passed=True,
                failures=[],
                metrics=PromptMetrics(latency_ms=1200),
                confirmation="not_requested",
            )
        ],
        started_at=started_at,
        ended_at=ended_at,
    )

    assert summary["record_type"] == "summary"
    assert summary["duration_ms"] == 12345
    assert summary["duration_seconds"] == 12.345
    assert summary["started_at"] == "2026-07-22T17:00:00+00:00"
    assert summary["ended_at"] == "2026-07-22T17:00:12.345000+00:00"
