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
            "Analise a base international_sales e adicione um gráfico ao "
            "dashboard CBMES",
            AnalyticsGoal.PUBLISH_CHART,
        ),
    ],
)
def test_planner_recognizes_analytics_goals(message: str, goal: AnalyticsGoal) -> None:
    assert AnalyticsTaskPlanner().plan(message).intent.goal is goal


def test_planner_prioritizes_dashboard_creation_over_chart_topics() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "Faça um dashboard AI_TEST_P103 dedicado à análise de dados de população global."
    )

    assert plan.intent.goal is AnalyticsGoal.CREATE_DASHBOARD
    assert plan.intent.target_dashboard == "ai_test_p103"
    assert plan.intent.chart_title is None


def test_planner_handles_portuguese_publish_synonym_and_source() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "Analise o banco international_sales, inclua um grafico com quantidade "
        "de vendas por ano no painel CBMES"
    )

    assert plan.intent.goal is AnalyticsGoal.PUBLISH_CHART
    assert plan.intent.source_hint == "international_sales"
    assert plan.intent.target_dashboard == "cbmes"
    assert plan.intent.metric == "count"
    assert plan.intent.time_grain == "year"
    assert {
        "list_databases",
        "create_chart",
        "list_dashboards",
        "add_chart_to_dashboard",
    } <= plan.tool_names


def test_planner_extracts_source_hint_from_leading_no_dataset_name() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "No international_sales, faça barras da quantidade vendida por categoria."
    )

    assert plan.intent.goal is AnalyticsGoal.CREATE_CHART
    assert plan.intent.source_hint == "international_sales"
    assert plan.intent.topic == "quantidade"
    assert plan.intent.metric == "quantity"
    assert plan.intent.dimension == "product_category"


def test_planner_treats_chart_in_current_dashboard_as_chart_request() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "Neste dashboard, crie um gráfico AI_TEST_P51 de receita anual usando "
        "international_sales."
    )

    assert plan.intent.goal is AnalyticsGoal.CREATE_CHART
    assert plan.intent.chart_title == "ai_test_p51"
    assert plan.intent.source_hint == "international_sales"


def test_planner_extracts_topic_after_analysis_preposition() -> None:
    plan = AnalyticsTaskPlanner().plan("Faça uma análise de vendas por país.")

    assert plan.intent.topic == "vendas"
    assert plan.intent.dimension == "country"


def test_planner_removes_stopwords_instead_of_using_them_as_topic() -> None:
    plan = AnalyticsTaskPlanner().plan("Mostre os dados por ano em barras")

    assert plan.intent.topic is None
    assert plan.intent.discovery_query is None


def test_planner_requests_clarification_only_when_publish_destination_is_missing() -> (
    None
):
    plan = AnalyticsTaskPlanner().plan("Crie um gráfico anual de vendas e publique")

    assert plan.intent.goal is AnalyticsGoal.PUBLISH_CHART
    assert plan.clarification == "Em qual dashboard o gráfico deve ser publicado?"


def test_planner_does_not_need_dashboard_word_when_publish_target_is_clear() -> None:
    plan = AnalyticsTaskPlanner().plan("Adicione um gráfico de vendas no CBMES")

    assert plan.intent.goal is AnalyticsGoal.PUBLISH_CHART
    assert plan.intent.target_dashboard == "cbmes"
    assert plan.clarification is None


def test_planner_builds_multilingual_discovery_query_for_generic_chart_request() -> (
    None
):
    plan = AnalyticsTaskPlanner().plan(
        "Elabore um gráfico em barras das vendas por ano."
    )

    assert plan.intent.goal is AnalyticsGoal.CREATE_CHART
    assert plan.intent.topic == "vendas"
    assert plan.intent.discovery_query is not None
    assert plan.intent.discovery_query.prompt_language == "pt-BR"
    assert {"vendas", "sales", "ventas", "ventes"} <= set(
        plan.intent.discovery_query.expanded_terms
    )


def test_planner_extracts_specific_metric_before_generic_sales_term() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "Crie o chart AI_TEST_P27 de vendas globais por ano usando video_game_sales."
    )

    assert plan.intent.source_hint == "video_game_sales"
    assert plan.intent.metric == "global_sales"


def test_planner_prioritizes_cost_for_cost_versus_revenue_prompt() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "Crie um gráfico AI_TEST_P14 de custo versus receita por região."
    )

    assert plan.intent.source_hint == "international_sales"
    assert plan.intent.metric == "cost"
    assert plan.intent.dimension == "region"
    assert plan.intent.chart_title == "ai_test_p14"


def test_planner_uses_international_sales_for_implicit_revenue_and_profit() -> None:
    revenue = AnalyticsTaskPlanner().plan(
        "Crie um gráfico de linha AI_TEST_P201 de receita ao longo do tempo."
    )
    profit = AnalyticsTaskPlanner().plan(
        "Crie um gráfico de área AI_TEST_P202 de lucro acumulado."
    )

    assert revenue.intent.source_hint == "international_sales"
    assert revenue.intent.metric == "revenue"
    assert profit.intent.source_hint == "international_sales"
    assert profit.intent.metric == "profit"


def test_planner_uses_birth_names_for_demographic_gender_requests() -> None:
    plan = AnalyticsTaskPlanner().plan(
        "Qual gênero de bebê foi mais frequente em cada década?"
    )

    assert plan.intent.source_hint == "birth_names"
    assert plan.intent.discovery_query is not None
    assert plan.intent.discovery_query.normalized_topic == "birth names"


def test_planner_preserves_requested_ai_test_resource_names() -> None:
    chart = AnalyticsTaskPlanner().plan(
        "Adicione ao CBMES um gráfico AI_TEST_P15 de receita por ano do international_sales."
    )
    dataset = AnalyticsTaskPlanner().plan(
        "Transforme a consulta salva AI_TEST_P19 em um dataset AI_TEST_P20."
    )
    saved_query = AnalyticsTaskPlanner().plan(
        "Crie uma consulta salva AI_TEST_P44 que traga população total por país e ano."
    )
    prefixed = AnalyticsTaskPlanner().plan(
        "Use dados de vendas e crie dataset, gráfico de barras anual e publique no "
        "CBMES com o prefixo AI_TEST_P50."
    )

    assert chart.intent.chart_title == "ai_test_p15"
    assert chart.intent.target_dashboard == "cbmes"
    assert chart.intent.source_hint == "international_sales"
    assert dataset.intent.source_hint == "ai_test_p19"
    assert dataset.intent.dataset_name == "ai_test_p20"
    assert dataset.intent.discovery_query is not None
    assert dataset.intent.discovery_query.normalized_topic == "ai test p19"
    assert saved_query.intent.saved_query_label == "ai_test_p44"
    assert prefixed.intent.output_prefix == "ai_test_p50"
    assert prefixed.intent.dataset_name == "ai_test_p50_dataset"
    assert prefixed.intent.chart_title == "ai_test_p50_chart"


def test_planner_handles_p16_to_p20_corrective_cases() -> None:
    publish = AnalyticsTaskPlanner().plan(
        "No dashboard CBMES, publique AI_TEST_P16: lucro por país com dados de "
        "international_sales."
    )
    virtual_dataset = AnalyticsTaskPlanner().plan(
        "Crie um dataset virtual AI_TEST_P17 de receita anual do international_sales."
    )
    saved_query = AnalyticsTaskPlanner().plan(
        "Crie uma consulta salva AI_TEST_P19 com vendas mensais de "
        "cleaned_sales_data."
    )
    materialized = AnalyticsTaskPlanner().plan(
        "Transforme a consulta salva AI_TEST_P19 em um dataset AI_TEST_P20."
    )

    assert publish.intent.goal is AnalyticsGoal.PUBLISH_CHART
    assert publish.intent.chart_title == "ai_test_p16"
    assert publish.intent.source_hint == "international_sales"
    assert publish.intent.target_dashboard == "cbmes"
    assert publish.intent.metric == "profit"
    assert publish.intent.dimension == "country"
    assert virtual_dataset.intent.goal is AnalyticsGoal.CREATE_DATASET
    assert virtual_dataset.intent.dataset_name == "ai_test_p17"
    assert virtual_dataset.intent.source_hint == "international_sales"
    assert virtual_dataset.intent.metric == "revenue"
    assert virtual_dataset.intent.time_grain == "year"
    assert saved_query.intent.goal is AnalyticsGoal.CREATE_QUERY
    assert saved_query.intent.saved_query_label == "ai_test_p19"
    assert saved_query.intent.source_hint == "cleaned_sales_data"
    assert saved_query.intent.time_grain == "month"
    assert materialized.intent.goal is AnalyticsGoal.CREATE_DATASET
    assert materialized.intent.source_hint == "ai_test_p19"
    assert materialized.intent.dataset_name == "ai_test_p20"


def test_planner_handles_p31_to_p40_corrective_cases() -> None:
    flights = AnalyticsTaskPlanner().plan(
        "Mostre os 10 aeroportos de origem com mais voos."
    )
    names = AnalyticsTaskPlanner().plan(
        "Faça um gráfico AI_TEST_P38 com os 10 nomes mais frequentes em birth_names."
    )

    assert flights.intent.goal is AnalyticsGoal.ANALYZE
    assert flights.intent.metric == "count"
    assert flights.intent.dimension == "ORIGIN_AIRPORT"
    assert flights.intent.discovery_query is not None
    assert "voos" in flights.intent.discovery_query.expanded_terms
    assert names.intent.goal is AnalyticsGoal.CREATE_CHART
    assert names.intent.chart_title == "ai_test_p38"
    assert names.intent.source_hint == "birth_names"
    assert names.intent.metric == "births"
    assert names.intent.dimension == "name"


def test_planner_handles_p41_to_p50_corrective_cases() -> None:
    life = AnalyticsTaskPlanner().plan(
        "Mostre a expectativa de vida por região ao longo do tempo."
    )
    materialized = AnalyticsTaskPlanner().plan(
        "Transforme AI_TEST_P44 no dataset AI_TEST_P45 e crie o chart "
        "AI_TEST_P45_POP."
    )
    explain_query = AnalyticsTaskPlanner().plan(
        "Explique o que faz a consulta salva data_hora_atual."
    )
    chart_query = AnalyticsTaskPlanner().plan(
        "Crie um gráfico usando a consulta salva data_hora_atual."
    )
    messages = AnalyticsTaskPlanner().plan(
        "Busque informações de chats ou mensagens na database examples e proponha "
        "uma análise, sem expor conteúdo das mensagens."
    )

    assert life.intent.metric == "life_expectancy"
    assert life.intent.dimension == "region"
    assert materialized.intent.goal is AnalyticsGoal.CREATE_CHART
    assert materialized.intent.source_hint == "ai_test_p44"
    assert materialized.intent.dataset_name == "ai_test_p45"
    assert materialized.intent.chart_title == "ai_test_p45_pop"
    assert explain_query.intent.goal is AnalyticsGoal.ANALYZE
    assert explain_query.intent.source_hint == "data_hora_atual"
    assert chart_query.intent.goal is AnalyticsGoal.CREATE_CHART
    assert chart_query.intent.source_hint == "data_hora_atual"
    assert messages.intent.discovery_query is not None
    assert "messages" in messages.intent.discovery_query.expanded_terms


def test_planner_uses_configured_agent_language_and_semantic_expander() -> None:
    calls: list[tuple[str, str]] = []
    planner = AnalyticsTaskPlanner(
        semantic_expander=lambda topic, language: calls.append((topic, language))
        or ["delinquency"]
    )

    plan = planner.plan("Crie um gráfico de inadimplência", prompt_language="fr-FR")

    assert plan.intent.discovery_query is not None
    assert plan.intent.discovery_query.prompt_language == "fr-FR"
    assert calls == [("inadimplencia", "fr-FR")]
