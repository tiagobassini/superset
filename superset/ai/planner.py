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
    chart_type: str | None = None
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
        "pizza",
        "pie",
        "area",
        "área",
        "pca",
        "beeswarm",
        "swarm",
        "sankey",
        "arc",
        "radial",
        "kpi",
        "kpis",
        "scorecard",
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
            "atual",
            "current",
            "selecionado",
            "selecionada",
            "selected",
            "este",
            "esta",
            "this",
            "neste",
            "nesta",
            "usar",
            "use",
            "using",
            "escolher",
            "escolha",
        }
    )
    _CONTEXT_SOURCE_HINTS = frozenset(
        {
            "atual",
            "current",
            "selecionado",
            "selecionada",
            "selected",
            "este",
            "esta",
            "this",
            "neste",
            "nesta",
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
    _DASHBOARD_PUBLISH_TOPICS = (
        "c-level",
        "churn",
        "compliance",
        "conformidade",
        "controle",
        "csat",
        "diversidade",
        "eficiencia",
        "eficiência",
        "esg",
        "executivo",
        "financeira",
        "heat map",
        "heat maps",
        "inovacao",
        "inovação",
        "integrado",
        "kpi",
        "kpis",
        "nps",
        "operacional",
        "operacoes",
        "operações",
        "orcamentario",
        "orçamentário",
        "pilar",
        "planejamento",
        "recursos humanos",
        "retencao",
        "retenção",
        "rh",
        "riscos",
        "satisfacao",
        "satisfação",
        "scorecard",
        "suprimentos",
        "sustentabilidade",
        "supply chain",
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
        (
            "revenue",
            ("receita", "receitas", "revenue", "faturamento", "ingresos", "recettes"),
        ),
        ("profit", ("lucro", "profit", "beneficio", "margem")),
        ("quantity_ordered", ("quantidade_ordered", "quantity ordered")),
        ("quantity", ("quantidade", "quantity", "quantidade_ordered")),
        ("cost", ("custo", "custos", "cost")),
        ("global_sales", ("vendas globais", "global sales", "global_sales")),
        ("na_sales", ("america do norte", "north america", "na_sales")),
        ("eu_sales", ("europa", "europe", "eu_sales")),
        ("sales", ("vendas", "sales", "ventas", "ventes")),
        ("delay", ("atraso", "atrasos", "delay", "delays")),
        ("cancellations", ("cancelamentos", "cancelled", "cancellations")),
        ("distance", ("distancia", "distance")),
        (
            "births",
            (
                "nascimento",
                "nascimentos",
                "birth",
                "births",
                "nome de bebe",
                "nome de bebê",
                "nomes de bebes",
                "nomes de bebês",
            ),
        ),
        ("population", ("populacao", "population")),
        ("life_expectancy", ("expectativa de vida", "life expectancy")),
        ("mortality", ("mortalidade", "mortality")),
    )
    _DIMENSION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("country", ("pais", "país", "country", "countries")),
        (
            "region",
            ("regiao", "região", "regioes", "region", "regions", "continente"),
        ),
        ("territory", ("territory", "territorio", "território")),
        ("product_category", ("categoria", "category", "categorias", "categories")),
        (
            "product_line",
            ("linha de produto", "linhas de produto", "product line", "product_line"),
        ),
        ("genre", ("genero", "gênero", "genre")),
        ("platform", ("plataforma", "platform")),
        ("publisher", ("editora", "publicadora", "publisher")),
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
        if dashboard in self._STOPWORDS:
            dashboard = None
        if goal is AnalyticsGoal.CREATE_DASHBOARD:
            dashboard = (
                self._first_ai_resource(normalized)
                or dashboard
                or self._dashboard_title_from_topic(normalized)
            )
        if goal is AnalyticsGoal.PUBLISH_CHART:
            dashboard = self._named_after_publish_target(normalized)
        metric = self._metric(normalized)
        dimension = self._dimension(normalized)
        if metric == "regional_sales":
            dimension = None
        chart_type = self._chart_type(normalized)
        topic = self._topic(normalized) or self._topic_from_request(normalized)
        output_prefix = self._output_prefix(normalized)
        exact_source_hint = source_hint in {
            "birth_names",
            "cleaned_sales_data",
            "data_hora_atual",
            "flights",
            "international_sales",
            "video_game_sales",
            "wb_health_population",
        }
        discovery_topic = (
            source_hint
            if exact_source_hint
            else (
                metric
                if metric
                in {
                    "cost",
                    "revenue_profit",
                    "revenue_population",
                    "sales_revenue_country",
                    "video_population",
                    "revenue_profit_population",
                    "message_count_by_user",
                    "flights_births_year",
                    "regional_sales",
                    "global_sales",
                    "na_sales",
                    "eu_sales",
                }
                else topic or source_hint or metric
            )
        )
        intent = AnalyticsIntent(
            goal=goal,
            topic=topic,
            source_hint=source_hint,
            target_dashboard=dashboard,
            chart_title=self._chart_output_name(normalized)
            or self._resource_name(normalized, "chart")
            or self._resource_name(normalized, "grafico")
            or (f"{output_prefix}_chart" if output_prefix else None)
            or (
                self._first_ai_resource(normalized)
                if goal
                in {AnalyticsGoal.CREATE_CHART, AnalyticsGoal.PUBLISH_CHART}
                else None
            ),
            dataset_name=self._dataset_resource_name(normalized)
            or (f"{output_prefix}_dataset" if output_prefix else None)
            or (
                self._first_ai_resource(normalized)
                if goal is AnalyticsGoal.CREATE_DATASET
                else None
            ),
            saved_query_label=self._saved_query_resource_name(normalized)
            or (f"{output_prefix}_query" if output_prefix else None),
            output_prefix=output_prefix,
            metric=metric,
            dimension=dimension,
            time_grain=self._time_grain(normalized),
            chart_type=chart_type,
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
        dashboard = any(word in message for word in cls._DASHBOARD_WORDS)
        create = any(word in message for word in cls._CREATE_WORDS)
        join_request = bool(
            re.search(r"\b(juntando|junte|join|una|une|cruzando)\b", message)
        )
        publish_target = cls._named_after_publish_target(message) if dashboard else None
        if publish and named_ai_chart:
            return AnalyticsGoal.PUBLISH_CHART
        if publish and chart:
            return AnalyticsGoal.PUBLISH_CHART
        if chart and dashboard and publish_target:
            return AnalyticsGoal.PUBLISH_CHART
        if dashboard and create and named_ai_chart and re.search(
            r"\b(multiplos graficos|multiplos gráficos|múltiplos gráficos|"
            r"sincronizacao|sincronização|monitoramento|tempo real)\b",
            message,
        ):
            return AnalyticsGoal.CREATE_DASHBOARD
        if dashboard and cls._dashboard_context_publication(message):
            return AnalyticsGoal.PUBLISH_CHART
        if dashboard and create and not chart:
            return AnalyticsGoal.CREATE_DASHBOARD
        if chart:
            return AnalyticsGoal.CREATE_CHART
        if cls._creates_dataset(message):
            return AnalyticsGoal.CREATE_DATASET
        if any(word in message for word in cls._QUERY_WORDS) and any(
            word in message for word in cls._CREATE_WORDS
        ):
            return AnalyticsGoal.CREATE_QUERY
        if join_request and named_ai_chart:
            return AnalyticsGoal.CREATE_DATASET
        if named_ai_chart and any(word in message for word in cls._CREATE_WORDS):
            return AnalyticsGoal.CREATE_CHART
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
    def _source_hint_for_metric(metric: str | None) -> str | None:
        if metric in {"cost", "profit", "revenue", "revenue_profit"}:
            return "international_sales"
        if metric in {
            "revenue_population",
            "revenue_profit_population",
            "message_count_by_user",
            "flights_births_year",
        }:
            return (
                "international_sales"
                if metric != "message_count_by_user"
                else "messages"
            )
        if metric == "sales_revenue_country":
            return "cleaned_sales_data"
        if metric == "video_population":
            return "video_game_sales"
        if metric == "regional_sales":
            return "video_game_sales"
        if metric == "flights_births_year":
            return "flights"
        return None

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
    def _dashboard_title_from_topic(cls, message: str) -> str | None:
        """Return a stable dashboard title when no explicit resource name exists."""

        topic = cls._topic(message) or cls._topic_from_request(message)
        return topic.title() if topic else None

    @classmethod
    def _source_hint(cls, message: str) -> str | None:
        skip_saved_query_output = re.search(
            r"\bcri\w*\s+(?:uma\s+)?consulta\s+salva\s+", message
        )
        known_source = re.search(
            r"(?:^|\s)(?:de|do|da|em|in|com|with|no|na|segundo)\s+"
            r"(cleaned_sales_data|international_sales|video_game_sales|flights|"
            r"birth_names|wb_health_population)\b",
            message,
        )
        if known_source:
            return known_source.group(1)
        if "data_hora_atual" in message:
            return "data_hora_atual"
        direct_source = re.search(
            r"\b(cleaned_sales_data|international_sales|video_game_sales|flights|"
            r"birth_names|wb_health_population)\b",
            message,
        )
        if direct_source:
            return direct_source.group(1)
        if re.search(r"\bnasciment\w*\b", message) and re.search(
            r"\bestad\w*\b", message
        ):
            return "birth_names"
        if re.search(r"\b(genero|gender|demograf)\w*\b", message) and re.search(
            r"\b(bebe|bebes|baby|babies|nome|nomes|name|names|demograf)\w*\b",
            message,
        ):
            return "birth_names"
        transformed_source = cls._named_after(message, r"(?:transforme|transform)\s+")
        if (
            transformed_source
            and transformed_source not in cls._STOPWORDS
            and (
                not transformed_source.startswith("ai_test_")
                or cls._creates_dataset(message)
            )
        ):
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

    @staticmethod
    def _chart_output_name(message: str) -> str | None:
        patterns = (
            r"\b(?:salve|salvar)\s+como\s+([A-Za-z0-9]+_[\w-]+)\b",
            r"\bchamad[ao]\s+([A-Za-z0-9]+_[\w-]+)\b",
            r"\bnomead[ao]\s+([A-Za-z0-9]+_[\w-]+)\b",
            r"\bcalled\s+([A-Za-z0-9]+_[\w-]+)\b",
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
        if re.search(r"\b(?:19|20)\d{2}\b", message):
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
    def _chart_type(message: str) -> str | None:
        if re.search(r"\b(pca|scatter|dispers[aã]o)\b", message):
            return "scatter"
        if re.search(r"\b(beeswarm|swarm)\b", message):
            return "scatter"
        if re.search(r"\b(sankey|arc diagram|arc|conex(?:ao|oes|ão|ões))\b", message):
            return "sankey"
        if re.search(r"\b(radial|ciclic[oa]s?|c[ií]clic[oa]s?)\b", message):
            return "pie"
        if re.search(r"\b(kpi|kpis|big number|numero|número|scorecard|painel)\b", message):
            return "big_number"
        if re.search(r"\b(pizza|pie|donut|rosca|anel|aneis|anéis|ring)\b", message):
            return "pie"
        if re.search(r"\b(area|área)\b", message):
            return "area"
        if re.search(
            r"\b(?:cri\w*|gere|monte|faça|faca)\s+(?:uma\s+)?tabela\b",
            message,
        ):
            return "table"
        if re.search(
            r"\b(?:visualizacao|grafico|chart)\s+(?:de\s+)?(tabela|table)\b",
            message,
        ):
            return "table"
        if re.search(r"\b(linha|line)\b", message):
            return "line"
        if re.search(r"\b(barra|barras|bar|bars)\b", message):
            return "bar"
        return None

    @classmethod
    def _dashboard_context_publication(cls, message: str) -> bool:
        """Treat dashboard/panel themes as publishable artifacts in dashboard context."""

        if cls._named_after_publish_target(message):
            return False
        if not re.search(r"\bai_test_[\w-]+\b", message):
            return False
        return any(term in message for term in cls._DASHBOARD_PUBLISH_TOPICS)

    @staticmethod
    def _named_after_publish_target(message: str) -> str | None:
        if match := re.search(
            r"(?:^|\s)(?:em|no|na|ao)\s+(?:dashboard|painel)\s+"
            r"[`\"']?([\w-]+)[`\"']?",
            message,
        ):
            return match.group(1)
        matches = re.findall(
            r"(?:^|\s)(?:em|no|na|ao)\s+(?:dashboard\s+)?[`\"']?([\w-]+)[`\"']?",
            message,
        )
        ignored = {
            "area",
            "atual",
            "chart",
            "contexto",
            "dashboard",
            "grafico",
            "gráfico",
            "kpi",
            "kpis",
            "monitoramento",
            "painel",
            "real",
            "tempo",
        }
        for value in reversed(matches):
            if value not in ignored:
                return value
        return None

    @staticmethod
    def _creates_dataset(message: str) -> bool:
        return bool(
            re.search(r"\bcri\w*\s+(?:um\s+|uma\s+)?dataset\b", message)
            or re.search(r"\bdataset\s+virtual\b", message)
            or re.search(
                r"\btransform\w*.+\b(?:em|no|na)\s+(?:um\s+|uma\s+)?dataset\b",
                message,
            )
        )

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
    def _metric(cls, message: str) -> str | None:  # noqa: C901
        if (
            "cleaned_sales_data" in message
            and "international_sales" in message
            and re.search(r"\b(juntando|junte|join|comparar|compare)\b", message)
        ):
            return "sales_revenue_country"
        if (
            "video" in message
            and re.search(r"\b(populacao|population)\b", message)
            and re.search(r"\b(global_sales|vendas globais)\b", message)
        ):
            return "video_population"
        if (
            "international_sales" in message
            and "wb_health_population" in message
            and re.search(r"\b(regiao|regiao|region)\b", message)
            and re.search(r"\b(profit|lucro)\b", message)
            and re.search(r"\b(populacao|population)\b", message)
        ):
            return "revenue_profit_population"
        if (
            "messages" in message
            and "users" in message
            and re.search(r"\b(mensagens|messages)\b", message)
            and re.search(r"\b(usuario|usuarios|user|users)\b", message)
        ):
            return "message_count_by_user"
        if "flights" in message and "birth_names" in message:
            return "flights_births_year"
        if re.search(
            r"\b(cancelado|cancelados|cancelada|canceladas|cancelamento|cancelamentos|cancelled|cancellations)\b",
            message,
        ):
            return "cancellations"
        if (
            re.search(r"\b(juntando|join|junte|combine|combinando)\b", message)
            and "international_sales" in message
            and "wb_health_population" in message
        ):
            return "revenue_population"
        if re.search(r"\b(receita|receitas|revenue)\b", message) and re.search(
            r"\b(populacao|population)\b", message
        ):
            return "revenue_population"
        if re.search(
            r"\b(ticket medio|ticket médio|media de lucro|média de lucro)\b",
            message,
        ):
            return "revenue"
        if re.search(r"\b(roi|retorno)\b", message):
            return "cost"
        if re.search(r"\b(margem|lucrativ)\w*\b", message) and re.search(
            r"\b(receita|revenue|custo|cost|regiao|região|categoria|produto)\w*\b",
            message,
        ):
            return "revenue_profit"
        if re.search(r"\b(custo|custos|cost)\b", message) and re.search(
            r"\b(receita|receitas|revenue|faturamento)\b", message
        ):
            return "cost"
        if re.search(r"\b(receita|revenue|faturamento)\b", message) and re.search(
            r"\b(profit|lucro)\b", message
        ):
            return "revenue_profit"
        if re.search(r"\b(receita|receitas|revenue|faturamento)\b", message):
            return "revenue"
        if re.search(r"\b(populacao|population)\b", message):
            return "population"
        if re.search(
            r"\b(nascimento|nascimentos|birth|births|bebe|bebes|bebê|bebês)\b",
            message,
        ) and re.search(r"\b(nome|nomes|name|names)\b", message):
            return "births"
        if re.search(r"\beuropa\b", message) and re.search(
            r"\b(america do norte|north america)\b", message
        ):
            return "regional_sales"
        if re.search(r"\b(na|eu|jp|global)\b", message) and re.search(
            r"\b(rad(ar)?|regia(?:o|oes)|region|sales|vendas)\b", message,
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
        if re.search(r"\b(product line|product_line|linha de produto)\b", message):
            return "product_line"
        if re.search(r"\b(territory|territorio|território)\b", message):
            return "territory"
        if re.search(r"\b(status|state|estado)\b", message):
            return "status"
        for dimension, aliases in cls._DIMENSION_ALIASES:
            if any(
                re.search(rf"\b{re.escape(alias)}\b", message) for alias in aliases
            ):
                return dimension
        if re.search(r"\b(produto|produtos|product|products|sku)\b", message):
            return "product"
        return None
