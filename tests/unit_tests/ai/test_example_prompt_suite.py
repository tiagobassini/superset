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

from pathlib import Path

from scripts.ai.run_example_prompt_suite import (
    build_oracle,
    evaluate_result,
    load_cases,
    PromptCase,
)


def test_load_cases_reads_all_documented_prompts() -> None:
    cases = load_cases(Path("docs/ai-integration/example-database-ai-prompts.md"))

    assert len(cases) == 50
    assert cases[0].id == "P01"
    assert cases[-1].id == "P50"


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
