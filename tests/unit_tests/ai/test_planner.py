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
"""Unit tests for deterministic analytics intent planning."""

import pytest

from superset.ai.planner import AnalyticsGoal, AnalyticsTaskPlanner


@pytest.mark.parametrize(
    ("message", "goal"),
    [
        ("Quais dados de vendas temos disponíveis?", AnalyticsGoal.ANALYZE),
        ("Crie um dataset da tabela orders", AnalyticsGoal.CREATE_DATASET),
        ("Faça uma consulta SQL de vendas por ano", AnalyticsGoal.CREATE_QUERY),
        ("Monte um gráfico de receita mensal", AnalyticsGoal.CREATE_CHART),
        ("Crie um painel executivo", AnalyticsGoal.CREATE_DASHBOARD),
        (
            "Analise a base international_sales e adicione um gráfico ao dashboard CBMES",
            AnalyticsGoal.PUBLISH_CHART,
        ),
    ],
)
def test_planner_recognizes_analytics_goals(
    message: str, goal: AnalyticsGoal
) -> None:
    assert AnalyticsTaskPlanner().plan(message).intent.goal is goal


def test_planner_handles_portuguese_publish_synonym_and_source() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "Analise o banco international_sales, inclua um grafico com quantidade de vendas por ano no painel CBMES"
    )

    assert plan.intent.goal is AnalyticsGoal.PUBLISH_CHART
    assert plan.intent.source_hint == "international_sales"
    assert plan.intent.target_dashboard == "cbmes"
    assert plan.intent.metric == "count"
    assert plan.intent.time_grain == "year"
    assert {"list_databases", "create_chart", "list_dashboards", "add_chart_to_dashboard"} <= plan.tool_names


def test_planner_requests_clarification_only_when_publish_destination_is_missing() -> None:
    plan = AnalyticsTaskPlanner().plan("Crie um gráfico anual de vendas e publique")

    assert plan.intent.goal is AnalyticsGoal.PUBLISH_CHART
    assert plan.clarification == "Em qual dashboard o gráfico deve ser publicado?"


def test_planner_does_not_need_dashboard_word_when_publish_target_is_clear() -> None:
    plan = AnalyticsTaskPlanner().plan("Adicione um gráfico de vendas no CBMES")

    assert plan.intent.goal is AnalyticsGoal.PUBLISH_CHART
    assert plan.intent.target_dashboard == "cbmes"
    assert plan.clarification is None
