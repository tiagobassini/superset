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
"""Deterministic intent planning for autonomous analytics requests."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from superset.ai.discovery import build_discovery_query, DiscoveryQuery

SemanticExpander = Callable[[str, str], Iterable[str]]


class AnalyticsGoal(StrEnum):
    """High-level outcomes recognized before provider tool selection."""

    ANALYZE = "analyze"
    CREATE_DATASET = "create_dataset"
    CREATE_CHART = "create_chart"
    CREATE_DASHBOARD = "create_dashboard"
    CREATE_QUERY = "create_query"
    PUBLISH_CHART = "create_chart_and_add_to_dashboard"


@dataclass(frozen=True)
class AnalyticsIntent:
    """Safe, provider-neutral interpretation of a user analytics request."""

    goal: AnalyticsGoal
    topic: str | None = None
    source_hint: str | None = None
    target_dashboard: str | None = None
    chart_title: str | None = None
    dataset_name: str | None = None
    saved_query_label: str | None = None
    output_prefix: str | None = None
    metric: str | None = None
    dimension: str | None = None
    time_grain: str | None = None
    discovery_query: DiscoveryQuery | None = None


@dataclass(frozen=True)
class AnalyticsPlan:
    """Intent, required tool names and any indispensable clarification."""

    intent: AnalyticsIntent
    tool_names: frozenset[str]
    clarification: str | None = None


class AnalyticsTaskPlanner:
    """Plan multi-domain analytics work without relying on model keywords alone."""

    _PUBLISH_VERBS = ("adicion", "inclu", "coloc", "publi", "insir")
    _CHART_WORDS = (
        "grafico",
        "chart",
        "visualizacao",
        "barra",
        "barras",
        "bar",
        "bars",
    )
    _DASHBOARD_WORDS = ("dashboard", "painel")
    _DATASET_WORDS = ("dataset", "tabela")
    _QUERY_WORDS = ("sql", "query", "consulta")
    _CREATE_WORDS = ("cri", "gere", "mont", "faca", "faça", "transform")
    _STOPWORDS = frozenset(
        {
            "a",
            "o",
            "as",
            "os",
            "de",
            "da",
            "das",
            "do",
            "dos",
            "por",
            "para",
            "com",
            "em",
            "no",
            "na",
            "ao",
            "the",
            "by",
            "of",
            "for",
            "with",
            "meu",
            "minha",
            "meus",
            "minhas",
            "my",
            "des",
            "del",
            "du",
            "par",
            "pour",
            "con",
            "ano",
            "anual",
            "year",
            "yearly",
            "annual",
            "annuelles",
            "tiempo",
            "tempo",
            "origem",
            "barras",
            "barra",
            "bar",
            "bars",
            "grafico",
            "chart",
            "dados",
            "base",
            "banco",
            "dataset",
            "tabela",
            "virtual",
        }
    )
    _TOPIC_TERMS = (
        "vendas",
        "venda",
        "sales",
        "sale",
        "ventas",
        "venta",
        "ventes",
        "vente",
        "receita",
        "revenue",
        "faturamento",
        "ingresos",
        "recettes",
        "lucro",
        "profit",
        "beneficio",
        "marge",
        "margem",
        "margin",
        "quantidade",
        "quantity",
        "custo",
        "cost",
        "videogames",
        "videogame",
        "jogos",
        "games",
        "voos",
        "voo",
        "flight",
        "flights",
        "atrasos",
        "atraso",
        "delay",
        "delays",
        "nascimentos",
        "nascimento",
        "nomes",
        "names",
        "birth",
        "births",
        "populacao",
        "population",
        "saude",
        "health",
        "mortalidade",
        "mortality",
        "global_sales",
        "na_sales",
        "eu_sales",
        "expectativa",
        "vida",
        "chats",
        "chat",
        "mensagens",
        "mensagem",
        "messages",
        "message",
        "usuarios",
        "usuários",
        "users",
    )
    _METRIC_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "count",
            (
                "quantidade de vendas",
                "quantidade de transacoes",
                "quantidade de pedidos",
                "mais voos",
                "numero de voos",
                "número de voos",
                "numero",
            ),
        ),
        ("revenue", ("receita", "revenue", "faturamento", "ingresos", "recettes")),
        ("profit", ("lucro", "profit", "beneficio")),
        ("quantity_ordered", ("quantidade_ordered", "quantity ordered")),
        ("quantity", ("quantidade", "quantity", "quantidade_ordered")),
        ("cost", ("custo", "cost")),
        ("global_sales", ("vendas globais", "global sales", "global_sales")),
        ("na_sales", ("america do norte", "north america", "na_sales")),
        ("eu_sales", ("europa", "europe", "eu_sales")),
        ("sales", ("vendas", "sales", "ventas", "ventes")),
        ("delay", ("atraso", "atrasos", "delay", "delays")),
        ("cancellations", ("cancelamentos", "cancelled", "cancellations")),
        ("distance", ("distancia", "distance")),
        ("births", ("nascimentos", "births")),
        ("population", ("populacao", "population")),
        ("life_expectancy", ("expectativa de vida", "life expectancy")),
        ("mortality", ("mortalidade", "mortality")),
    )
    _DIMENSION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("country", ("pais", "país", "country", "countries")),
        ("region", ("regiao", "região", "region", "regions")),
        ("territory", ("territory", "territorio", "território")),
        ("product_category", ("categoria", "category", "categorias", "categories")),
        ("product_line", ("linha de produto", "product line", "product_line")),
        ("genre", ("genero", "gênero", "genre")),
        ("platform", ("plataforma", "platform")),
        ("publisher", ("publicadora", "publisher")),
        ("AIRLINE", ("companhia aerea", "companhia aérea", "airline")),
        (
            "ORIGIN_AIRPORT",
            (
                "aeroporto de origem",
                "aeroportos de origem",
                "origin airport",
                "origin_airport",
            ),
        ),
        ("name", ("nome", "nomes", "name", "names")),
        ("state", ("estado", "state")),
        ("gender", ("genero", "gênero", "sexo", "gender")),
    )

    _DISCOVERY_TOOLS = frozenset(
        {
            "list_databases",
            "list_database_tables",
            "get_table_schema",
            "list_datasets",
            "get_dataset_schema",
            "profile_dataset",
        }
    )
    _CHART_TOOLS = frozenset(
        {"list_datasets", "get_dataset_schema", "list_charts", "create_chart"}
    )
    _DASHBOARD_TOOLS = frozenset(
        {
            "list_dashboards",
            "list_charts",
            "create_dashboard",
            "add_chart_to_dashboard",
        }
    )

    def __init__(self, semantic_expander: SemanticExpander | None = None) -> None:
        """Create a deterministic planner with optional bounded provider hints."""
        self.semantic_expander = semantic_expander

    def plan(self, message: str, prompt_language: str | None = None) -> AnalyticsPlan:
        """Return the goal and tools needed to safely advance the request."""
        normalized = self._normalize(message)
        goal = self._goal(normalized)
        source_hint = self._source_hint(normalized)
        dashboard = self._named_after(normalized, r"(?:dashboard|painel)\s+")
        if goal is AnalyticsGoal.PUBLISH_CHART and dashboard is None:
            dashboard = self._named_after_publish_target(normalized)
        topic = self._topic(normalized) or self._topic_from_request(normalized)
        metric = self._metric(normalized)
        output_prefix = self._output_prefix(normalized)
        discovery_topic = topic or source_hint or metric
        intent = AnalyticsIntent(
            goal=goal,
            topic=topic,
            source_hint=source_hint,
            target_dashboard=dashboard,
            chart_title=self._resource_name(normalized, "chart")
            or self._resource_name(normalized, "grafico")
            or (f"{output_prefix}_chart" if output_prefix else None)
            or (
                self._first_ai_resource(normalized)
                if goal
                in {AnalyticsGoal.CREATE_CHART, AnalyticsGoal.PUBLISH_CHART}
                else None
            ),
            dataset_name=self._dataset_resource_name(normalized)
            or (f"{output_prefix}_dataset" if output_prefix else None),
            saved_query_label=self._saved_query_resource_name(normalized)
            or (f"{output_prefix}_query" if output_prefix else None),
            output_prefix=output_prefix,
            metric=metric,
            dimension=self._dimension(normalized),
            time_grain=self._time_grain(normalized),
            discovery_query=(
                build_discovery_query(
                    discovery_topic, prompt_language, self.semantic_expander
                )
                if discovery_topic
                else None
            ),
        )
        clarification = None
        if goal is AnalyticsGoal.PUBLISH_CHART and not dashboard:
            clarification = "Em qual dashboard o gráfico deve ser publicado?"
        return AnalyticsPlan(intent, self._tools_for(goal), clarification)

    @classmethod
    def _goal(cls, message: str) -> AnalyticsGoal:
        publish = any(word in message for word in cls._PUBLISH_VERBS)
        chart = any(word in message for word in cls._CHART_WORDS)
        named_ai_chart = bool(re.search(r"\bai_test_[\w-]+\b", message))
        if publish and named_ai_chart:
            return AnalyticsGoal.PUBLISH_CHART
        if publish and chart:
            return AnalyticsGoal.PUBLISH_CHART
        if any(word in message for word in cls._DASHBOARD_WORDS) and any(
            word in message for word in cls._CREATE_WORDS
        ):
            return AnalyticsGoal.CREATE_DASHBOARD
        if chart:
            return AnalyticsGoal.CREATE_CHART
        if any(word in message for word in cls._DATASET_WORDS) and any(
            word in message for word in cls._CREATE_WORDS
        ):
            return AnalyticsGoal.CREATE_DATASET
        if any(word in message for word in cls._QUERY_WORDS) and any(
            word in message for word in cls._CREATE_WORDS
        ):
            return AnalyticsGoal.CREATE_QUERY
        return AnalyticsGoal.ANALYZE

    @classmethod
    def _tools_for(cls, goal: AnalyticsGoal) -> frozenset[str]:
        if goal is AnalyticsGoal.PUBLISH_CHART:
            return (
                cls._DISCOVERY_TOOLS
                | cls._CHART_TOOLS
                | cls._DASHBOARD_TOOLS
                | frozenset({"create_dataset"})
            )
        if goal is AnalyticsGoal.CREATE_CHART:
            return cls._DISCOVERY_TOOLS | cls._CHART_TOOLS | frozenset(
                {"create_dataset", "get_saved_query"}
            )
        if goal is AnalyticsGoal.CREATE_DASHBOARD:
            return cls._DISCOVERY_TOOLS | cls._CHART_TOOLS | cls._DASHBOARD_TOOLS
        if goal is AnalyticsGoal.CREATE_DATASET:
            return cls._DISCOVERY_TOOLS | frozenset({"create_dataset"})
        if goal is AnalyticsGoal.CREATE_QUERY:
            return cls._DISCOVERY_TOOLS | frozenset(
                {
                    "run_sql_query",
                    "save_sql_query",
                    "list_saved_queries",
                    "get_saved_query",
                }
            )
        return cls._DISCOVERY_TOOLS | frozenset({"list_charts", "list_dashboards"})

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            "".join(
                char
                for char in unicodedata.normalize("NFD", value.casefold())
                if unicodedata.category(char) != "Mn"
            ).split()
        )

    @staticmethod
    def _named_after(message: str, prefix: str) -> str | None:
        match = re.search(prefix + r"[`\"']?([\w-]+)[`\"']?", message)
        return match.group(1) if match else None

    @classmethod
    def _source_hint(cls, message: str) -> str | None:
        skip_saved_query_output = re.search(
            r"\bcri\w*\s+(?:uma\s+)?consulta\s+salva\s+", message
        )
        transformed_source = cls._named_after(message, r"(?:transforme|transform)\s+")
        if transformed_source and transformed_source not in cls._STOPWORDS:
            return transformed_source
        typed = cls._named_after(
            message,
            r"(?:banco|base de dados|dataset|tabela|consulta salva)\s+"
            r"(?!virtual\b)",
        )
        if typed and typed not in cls._STOPWORDS and not skip_saved_query_output:
            return typed
        indirect = cls._named_after(
            message,
            r"(?:usando|use|using)\s+(?:o\s+|a\s+)?"
            r"(?:dataset\s+|tabela\s+|consulta\s+salva\s+)?",
        )
        if indirect and indirect not in cls._STOPWORDS:
            return indirect
        with_typed_source = cls._named_after(
            message,
            r"(?:com|with)\s+(?:o\s+|a\s+)?"
            r"(?:dados\s+de\s+|dataset\s+|tabela\s+|consulta\s+salva\s+)",
        )
        if with_typed_source:
            return with_typed_source
        known_source = re.search(
            r"(?:^|\s)(?:de|do|da|em|in|com|with)\s+"
            r"(cleaned_sales_data|international_sales|video_game_sales|flights|"
            r"birth_names|wb_health_population)\b",
            message,
        )
        if known_source:
            return known_source.group(1)
        typed_from_source = re.search(
            r"(?:^|\s)(?:de|do|da)\s+"
            r"(?:dataset\s+|tabela\s+|consulta\s+salva\s+)?"
            r"([A-Za-z0-9]+_[\w-]+)",
            message,
        )
        if typed_from_source:
            return typed_from_source.group(1)
        match = re.search(
            r"(?:^|\s)(?:no|na)\s+(?!dashboard\b|painel\b)"
            r"(?:dataset\s+|tabela\s+|consulta\s+salva\s+)?"
            r"([A-Za-z0-9]+_[\w-]+)",
            message,
        )
        return match.group(1) if match else None

    @staticmethod
    def _resource_name(message: str, label: str) -> str | None:
        patterns = (
            rf"\b{re.escape(label)}\s+([A-Za-z0-9]+_[\w-]+)\b",
            rf"\b([A-Za-z0-9]+_[\w-]+)\s+(?:como|as)\s+{re.escape(label)}\b",
        )
        for pattern in patterns:
            if match := re.search(pattern, message):
                return match.group(1)
        return None

    @classmethod
    def _dataset_resource_name(cls, message: str) -> str | None:
        patterns = (
            r"\bdataset\s+(?:virtual\s+)?([A-Za-z0-9]+_[\w-]+)\b",
            r"\b([A-Za-z0-9]+_[\w-]+)\s+(?:como|as)\s+dataset\b",
        )
        for pattern in patterns:
            if match := re.search(pattern, message):
                return match.group(1)
        return None

    @classmethod
    def _saved_query_resource_name(cls, message: str) -> str | None:
        patterns = (
            r"\bconsulta\s+salva\s+([A-Za-z0-9]+_[\w-]+)\b",
            r"\b([A-Za-z0-9]+_[\w-]+)\s+(?:como|as)\s+consulta\s+salva\b",
        )
        for pattern in patterns:
            if match := re.search(pattern, message):
                return match.group(1)
        return None

    @staticmethod
    def _first_ai_resource(message: str) -> str | None:
        match = re.search(r"\b(AI_TEST_[A-Za-z0-9_]+)\b", message, re.IGNORECASE)
        return match.group(1).casefold() if match else None

    @staticmethod
    def _output_prefix(message: str) -> str | None:
        match = re.search(r"\bprefixo\s+([A-Za-z0-9]+_[\w-]+)\b", message)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _time_grain(message: str) -> str | None:
        if any(
            term in message
            for term in (
                "por ano",
                "por año",
                "by year",
                "per year",
                "par an",
                "anual",
                "yearly",
                "annual",
                "annuel",
                "annuelles",
            )
        ):
            return "year"
        if any(
            term in message
            for term in (
                "por mes",
                "por mês",
                "mensal",
                "mensais",
                "monthly",
                "by month",
                "per month",
            )
        ):
            return "month"
        return None

    @staticmethod
    def _named_after_publish_target(message: str) -> str | None:
        match = re.search(
            r"(?:em|no|na|ao)\s+(?:dashboard\s+)?[`\"']?([\w-]+)[`\"']?", message
        )
        return match.group(1) if match else None

    @staticmethod
    def _topic(message: str) -> str | None:
        match = re.search(
            r"(?:analise|analisar)\s+"
            r"(?:(?:a|o|as|os|de|da|do|das|dos)\s+)?"
            r"(?:base\s+de\s+dados\s+|banco\s+)?([\w-]+)",
            message,
        )
        if not match:
            return None
        topic = match.group(1)
        return None if topic in AnalyticsTaskPlanner._STOPWORDS else topic

    @staticmethod
    def _topic_from_request(message: str) -> str | None:
        """Extract a likely subject from ordinary chart requests.

        This only provides a discovery hint. It never selects a data source or
        replaces the schema-based validation performed by later workflow steps.
        """
        for term in AnalyticsTaskPlanner._TOPIC_TERMS:
            if re.search(rf"\b{term}\b", message):
                return term
        matches = re.findall(
            r"(?:da|das|do|dos|de|des|del|du|of)\s+([\w-]+)", message
        )
        return next(
            (
                value
                for value in reversed(matches)
                if value not in AnalyticsTaskPlanner._STOPWORDS
            ),
            None,
        )

    @classmethod
    def _metric(cls, message: str) -> str | None:
        if re.search(r"\bcusto\b", message) and re.search(
            r"\b(receita|revenue|faturamento)\b", message
        ):
            return "cost"
        if re.search(r"\beuropa\b", message) and re.search(
            r"\b(america do norte|north america)\b", message
        ):
            return "regional_sales"
        if re.search(r"\bnomes?\b", message) and re.search(
            r"\bfrequentes?\b", message
        ):
            return "births"
        if re.search(r"\bexpectativa\b", message) and re.search(
            r"\bvida\b", message
        ):
            return "life_expectancy"
        for metric, aliases in cls._METRIC_ALIASES:
            if any(
                re.search(rf"\b{re.escape(alias)}\b", message) for alias in aliases
            ):
                return metric
        return None

    @classmethod
    def _dimension(cls, message: str) -> str | None:
        for dimension, aliases in cls._DIMENSION_ALIASES:
            if any(
                re.search(rf"\b{re.escape(alias)}\b", message) for alias in aliases
            ):
                return dimension
        return None
