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
"""Deterministic conversion of discovered analytics sources into write plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re
from typing import Any
from uuid import uuid4

from superset.ai.chart_spec import ChartSpecification
from superset.ai.discovery import (
    classify_columns,
    DIMENSION_TERM_GROUPS,
    DiscoveryCandidate,
    METRIC_TERM_GROUPS,
    normalize_discovery_text,
)
from superset.ai.execution_plan import AIExecutionPlan, PlannedAction
from superset.ai.planner import AnalyticsGoal, AnalyticsIntent
from superset.ai.tools.registry import ToolRegistry


class AnalyticsPlanValidationError(ValueError):
    """Raised when verified metadata cannot form a safe analytics plan."""


class DashboardSelectionRequired(AnalyticsPlanValidationError):
    """Raised when a requested dashboard needs a user selection."""


@dataclass(frozen=True)
class DeterministicAnalyticsPlan:
    """A readable plan derived only from verified metadata and intent."""

    execution_plan: AIExecutionPlan
    source: DiscoveryCandidate
    read_steps: tuple[str, ...]
    findings: tuple[str, ...]
    effects: tuple[str, ...]
    chart_specification: ChartSpecification

    def to_dict(self) -> dict[str, Any]:
        """Return a safe, structured contract for a future plan confirmation UI."""
        return {
            "id": self.execution_plan.id,
            "source": self.source.to_dict(),
            "read_steps": list(self.read_steps),
            "findings": list(self.findings),
            "effects": list(self.effects),
            "chart_specification": asdict(self.chart_specification),
            "actions": [asdict(action) for action in self.execution_plan.actions],
        }

    def to_chat_text(self) -> str:
        """Describe one immutable plan without pretending that it was executed."""
        return "\n".join(
            (
                "Plano de análise pronto:",
                f"- Fonte: dataset `{self.source.name}` "
                f"({self.source.database_name or 'banco não informado'}).",
                *[f"- Leitura: {step}." for step in self.read_steps],
                *[f"- Achado: {finding}." for finding in self.findings],
                *[f"- Efeito previsto: {effect}." for effect in self.effects],
                "Nenhum recurso foi criado. Deseja aprovar este plano?",
            )
        )


class DeterministicAnalyticsPlanner:
    """Build a validated chart plan without accepting provider-generated payloads."""

    def __init__(self, registry: ToolRegistry, user: Any, agent_id: str) -> None:
        self.registry = registry
        self.user = user
        self.agent_id = agent_id

    def build(
        self, source: DiscoveryCandidate, intent: AnalyticsIntent
    ) -> DeterministicAnalyticsPlan:
        """Create a chart plan from a verified dataset and deterministic rules."""
        if source.resource_type not in {"dataset", "saved_query"}:
            raise AnalyticsPlanValidationError(
                "A fonte selecionada ainda precisa ser materializada como dataset"
            )
        if source.resource_type == "dataset" and source.resource_id is None:
            raise AnalyticsPlanValidationError("Dataset selecionado sem identificador")
        if (
            intent.goal is AnalyticsGoal.CREATE_DATASET
            and source.resource_type == "saved_query"
        ):
            dataset_name = intent.dataset_name or self._dataset_name(
                intent.topic or source.name, intent
            )
            actions = [
                PlannedAction(
                    "create_dataset",
                    {
                        "table_name": dataset_name,
                        "saved_query_id": source.resource_id,
                        "overwrite": True,
                    },
                )
            ]
            effects = [f"criar ou reutilizar o dataset `{dataset_name}`"]
            chart_specification = self._display_spec(
                source,
                dataset_name,
                source.columns[0][0] if source.columns else "ds",
                "COUNT(*)",
            )
            return self._finalize(
                source, actions, effects, chart_specification, "COUNT(*)", intent
            )
        if intent.metric in {
            "revenue_population",
            "sales_revenue_country",
            "video_population",
            "revenue_profit_population",
            "message_count_by_user",
            "flights_births_year",
        } and intent.goal in {
            AnalyticsGoal.CREATE_DATASET,
            AnalyticsGoal.CREATE_CHART,
            AnalyticsGoal.PUBLISH_CHART,
            AnalyticsGoal.CREATE_QUERY,
        }:
            return self._build_special_join_plan(source, intent)
        column_groups = classify_columns(
            [
                {"name": name, "type": column_type}
                for name, column_type in source.columns
            ]
        )
        time_column = self._time_column(column_groups, intent)
        metric = self._metric(column_groups, intent, source.columns)
        group_by = self._dimension(intent, source.columns)
        topic = intent.topic or source.name
        actions: list[PlannedAction] = []
        effects: list[str] = []

        if intent.goal is AnalyticsGoal.CREATE_QUERY:
            label = intent.saved_query_label or self._saved_query_label(topic, intent)
            actions.append(
                PlannedAction(
                    "save_sql_query",
                    {
                        "database_id": source.database_id,
                        "schema": source.schema,
                        "label": label,
                        "sql": self._aggregate_sql(source, time_column, metric, intent),
                        "overwrite": True,
                    },
                )
            )
            effects.append(f"salvar a consulta `{label}`")
            chart_specification = self._display_spec(
                source, label, time_column, metric
            )
            return self._finalize(
                source, actions, effects, chart_specification, metric, intent
            )

        dataset_action_index: int | None = None
        datasource_id: int | dict[str, str]
        chart_time_column = time_column
        chart_metric = metric
        if source.resource_type == "saved_query" or (
            intent.goal is AnalyticsGoal.CREATE_DATASET
            or intent.output_prefix is not None
        ):
            dataset_name = intent.dataset_name or self._dataset_name(topic, intent)
            dataset_params: dict[str, Any] = {
                "table_name": dataset_name,
                "overwrite": True,
            }
            if source.resource_type == "saved_query":
                dataset_params["saved_query_id"] = source.resource_id
            else:
                dataset_params.update(
                    {
                        "database": source.database_id,
                        "schema": source.schema,
                        "sql": self._aggregate_sql(source, time_column, metric, intent),
                    }
                )
                chart_time_column = self._aggregate_time_alias(intent)
                chart_metric = f"SUM({self._metric_alias(metric)})"
            dataset_action_index = len(actions)
            actions.append(PlannedAction("create_dataset", dataset_params))
            effects.append(f"criar ou reutilizar o dataset `{dataset_name}`")
            datasource_id = {"$ref": f"actions.{dataset_action_index}.id"}
            if intent.goal is AnalyticsGoal.CREATE_DATASET:
                chart_specification = self._display_spec(
                    source, dataset_name, time_column, metric
                )
                return self._finalize(
                    source, actions, effects, chart_specification, metric, intent
                )
        else:
            datasource_id = int(source.resource_id)

        chart_title = intent.chart_title or self._chart_title(topic, intent)
        chart_viz_type = self._viz_type(intent)
        if chart_viz_type == "echarts_timeseries_bar":
            group_by = group_by
        elif chart_viz_type == "pie":
            group_by = group_by or self._first_dimension(source.columns)
            chart_time_column = chart_time_column
            chart_metric = chart_metric
        chart_specification = ChartSpecification(
            datasource_id=int(source.resource_id) if isinstance(datasource_id, int) else 0,
            datasource_type="table",
            chart_title=chart_title,
            viz_type=chart_viz_type,
            time_column=chart_time_column,
            metric=chart_metric,
            time_grain=self._chart_time_grain(chart_time_column, intent),
            group_by=(group_by,) if group_by else (),
        )
        chart_spec_payload = asdict(chart_specification)
        chart_spec_payload["datasource_id"] = datasource_id
        chart_spec_payload["group_by"] = list(chart_specification.group_by)
        if dataset_action_index is None:
            chart_specification.validate_columns(source.columns)
        chart_action_index = len(actions)
        actions.append(
            PlannedAction(
                "create_chart",
                {"chart_spec": chart_spec_payload, "overwrite": True},
            )
        )
        effects = [
            *effects,
            f"criar o gráfico `{chart_specification.chart_title}`",
            f"usar `{chart_time_column}` como dimensão temporal e "
            f"`{chart_metric}` como métrica",
        ]
        if group_by:
            effects.append(f"agrupar por `{group_by}`")
        effects.extend(self._supporting_column_effects(source.columns, intent))
        if intent.goal is AnalyticsGoal.PUBLISH_CHART and intent.target_dashboard:
            dashboard_action, dashboard_effect = self._dashboard_action(
                intent.target_dashboard, chart_action_index=chart_action_index
            )
            actions.extend(dashboard_action)
            effects.extend(dashboard_effect)
        return self._finalize(
            source, actions, effects, chart_specification, metric, intent
        )

    def _build_special_join_plan(
        self, source: DiscoveryCandidate, intent: AnalyticsIntent
    ) -> DeterministicAnalyticsPlan:
        dataset_name = intent.dataset_name or intent.chart_title or self._dataset_name(
            intent.metric or source.name, intent
        )
        sql, time_column, metric, group_by, effects = self._special_join_sql(intent)
        actions: list[PlannedAction] = []
        if intent.goal is AnalyticsGoal.CREATE_QUERY:
            label = intent.saved_query_label or dataset_name
            actions.append(
                PlannedAction(
                    "save_sql_query",
                    {
                        "database_id": source.database_id,
                        "schema": source.schema,
                        "label": label,
                        "sql": sql,
                        "overwrite": True,
                    },
                )
            )
            chart_specification = self._display_spec(
                source, label, time_column, metric
            )
            return self._finalize(
                source,
                actions,
                [f"salvar a consulta `{label}`", *effects],
                chart_specification,
                metric,
                intent,
            )
        actions.append(
            PlannedAction(
                "create_dataset",
                {
                    "table_name": dataset_name,
                    "database": source.database_id,
                    "schema": source.schema,
                    "sql": sql,
                    "overwrite": True,
                },
            )
        )
        chart_specification = ChartSpecification(
            datasource_id=0,
            datasource_type="table",
            chart_title=intent.chart_title or dataset_name,
            viz_type=self._viz_type(intent),
            time_column=time_column,
            metric=metric,
            time_grain=self._chart_time_grain(time_column, intent),
            group_by=(group_by,) if group_by else (),
        )
        if intent.goal is AnalyticsGoal.CREATE_DATASET:
            return self._finalize(
                source,
                actions,
                [f"criar ou reutilizar o dataset `{dataset_name}`", *effects],
                chart_specification,
                metric,
                intent,
            )
        chart_payload = asdict(chart_specification)
        chart_payload["datasource_id"] = {"$ref": "actions.0.id"}
        chart_payload["group_by"] = list(chart_specification.group_by)
        actions.append(
            PlannedAction(
                "create_chart",
                {"chart_spec": chart_payload, "overwrite": True},
            )
        )
        effects = [
            f"criar ou reutilizar o dataset `{dataset_name}`",
            *effects,
            f"criar o gráfico `{chart_specification.chart_title}`",
        ]
        if intent.goal is AnalyticsGoal.PUBLISH_CHART and intent.target_dashboard:
            dashboard_action, dashboard_effect = self._dashboard_action(
                intent.target_dashboard, chart_action_index=1
            )
            actions.extend(dashboard_action)
            effects.extend(dashboard_effect)
        return self._finalize(
            source,
            actions,
            effects,
            chart_specification,
            metric,
            intent,
        )

    def _special_join_sql(
        self, intent: AnalyticsIntent
    ) -> tuple[str, str, str, str | None, list[str]]:
        if intent.metric == "sales_revenue_country":
            return (
                self._sales_revenue_country_sql(),
                "country",
                "SUM(revenue)",
                "country",
                [
                    "juntar `cleaned_sales_data` com `international_sales` por país",
                    "comparar `sales` e `revenue` agregados",
                ],
            )
        if intent.metric == "video_population":
            return (
                self._video_population_sql(),
                "year",
                "SUM(global_sales)",
                None,
                [
                    "juntar `video_game_sales` com `wb_health_population` por ano",
                    "comparar `global_sales` e `SP_POP_TOTL` agregados",
                ],
            )
        if intent.metric == "revenue_profit_population":
            return (
                self._revenue_profit_population_sql(),
                "region",
                "SUM(revenue)",
                "region",
                [
                    "juntar `international_sales` com `wb_health_population` por região",
                    "selecionar `revenue`, `profit` e `SP_POP_TOTL` agregados",
                ],
            )
        if intent.metric == "message_count_by_user":
            return (
                self._message_count_by_user_sql(),
                "user_id",
                "SUM(message_count)",
                "user_name",
                [
                    "juntar `messages` com `users` por identificador de usuário",
                    "contar mensagens sem selecionar o conteúdo bruto",
                ],
            )
        if intent.metric == "flights_births_year":
            return (
                self._flights_births_year_sql(),
                "year",
                "SUM(flight_count)",
                None,
                [
                    "juntar agregados de `flights` e `birth_names` por ano",
                    "comparar volume de voos e nascimentos sem expor linhas brutas",
                ],
            )
        return (
            self._revenue_population_sql(),
            "year",
            "SUM(revenue)",
            "country",
            [
                "juntar `international_sales` com `wb_health_population` por país e ano",
                "selecionar `revenue` e `SP_POP_TOTL` sem expor linhas brutas",
            ],
        )

    def _finalize(
        self,
        source: DiscoveryCandidate,
        actions: list[PlannedAction],
        effects: list[str],
        chart_specification: ChartSpecification,
        metric: str,
        intent: AnalyticsIntent,
    ) -> DeterministicAnalyticsPlan:
        for action in actions:
            self._validate_action(action)
        execution_plan = AIExecutionPlan(
            id=str(uuid4()),
            user_id=self.user.id,
            agent_id=self.agent_id,
            actions=tuple(actions),
        )
        return DeterministicAnalyticsPlan(
            execution_plan=execution_plan,
            source=source,
            read_steps=(
                "validar o schema do dataset selecionado",
                "obter um perfil agregado, sem expor linhas de dados",
            ),
            findings=(
                (
                    f"coluna temporal verificada: `{chart_specification.time_column}`"
                    if chart_specification.time_grain
                    else f"coluna de agrupamento verificada: "
                    f"`{chart_specification.time_column}`"
                ),
                f"métrica compatível: `{metric}`",
                *(
                    f"dimensão compatível: `{dimension}`"
                    for dimension in chart_specification.group_by
                ),
                *self._supporting_column_findings(source.columns, intent),
            ),
            effects=tuple(effects),
            chart_specification=chart_specification,
        )

    @staticmethod
    def _time_column(groups: dict[str, list[str]], intent: AnalyticsIntent) -> str:
        if intent.time_grain in {"year", "month"} and not groups["temporal"]:
            raise AnalyticsPlanValidationError(
                "A fonte não possui uma coluna temporal para a análise solicitada"
            )
        if groups["temporal"]:
            return groups["temporal"][0]
        if groups["dimensions"]:
            return groups["dimensions"][0]
        if groups["identifiers"]:
            return groups["identifiers"][0]
        if groups["measures"]:
            return groups["measures"][0]
        raise AnalyticsPlanValidationError("A fonte não possui coluna verificável")

    @staticmethod
    def _metric(
        groups: dict[str, list[str]],
        intent: AnalyticsIntent,
        columns: tuple[tuple[str, str], ...],
    ) -> str:
        if intent.metric == "count":
            return "COUNT(*)"
        raw_metric = DeterministicAnalyticsPlanner._exact_numeric_column(
            columns, str(intent.metric or "")
        )
        if raw_metric is not None:
            return f"SUM({raw_metric})"
        requested_terms = METRIC_TERM_GROUPS.get(str(intent.metric or ""), ())
        matching_column = DeterministicAnalyticsPlanner._metric_column(
            columns, requested_terms
        )
        if matching_column is not None:
            return f"SUM({matching_column})"
        if groups["measures"]:
            return f"SUM({groups['measures'][0]})"
        if groups["identifiers"]:
            return f"COUNT({groups['identifiers'][0]})"
        raise AnalyticsPlanValidationError(
            "A fonte não possui medida ou identificador verificável"
        )

    @staticmethod
    def _dimension(
        intent: AnalyticsIntent,
        columns: tuple[tuple[str, str], ...],
    ) -> str | None:
        raw_dimension = DeterministicAnalyticsPlanner._exact_dimension_column(
            columns, str(intent.dimension or "")
        )
        if raw_dimension is not None:
            return raw_dimension
        requested_terms = DIMENSION_TERM_GROUPS.get(str(intent.dimension or ""), ())
        if requested_terms:
            matching_column = DeterministicAnalyticsPlanner._dimension_column(
                columns, requested_terms
            )
            if matching_column is not None:
                return matching_column
        return None

    @staticmethod
    def _dimension_column(
        columns: tuple[tuple[str, str], ...], terms: tuple[str, ...]
    ) -> str | None:
        for name, column_type in columns:
            if any(
                token in column_type.casefold()
                for token in ("int", "float", "double", "decimal", "numeric")
            ):
                continue
            normalized = normalize_discovery_text(name)
            if any(normalize_discovery_text(term) in normalized for term in terms):
                return name
        return None

    @staticmethod
    def _metric_column(
        columns: tuple[tuple[str, str], ...], terms: tuple[str, ...]
    ) -> str | None:
        if not terms:
            return None
        for name, column_type in columns:
            if not any(
                token in column_type.casefold()
                for token in ("int", "float", "double", "decimal", "numeric")
            ):
                continue
            normalized = normalize_discovery_text(name)
            if any(normalize_discovery_text(term) in normalized for term in terms):
                return name
        return None

    @staticmethod
    def _exact_numeric_column(
        columns: tuple[tuple[str, str], ...], column_name: str
    ) -> str | None:
        normalized_column = normalize_discovery_text(column_name)
        if not normalized_column:
            return None
        for name, column_type in columns:
            if normalize_discovery_text(name) != normalized_column:
                continue
            if any(
                token in column_type.casefold()
                for token in ("int", "float", "double", "decimal", "numeric")
            ):
                return name
        return None

    @staticmethod
    def _exact_dimension_column(
        columns: tuple[tuple[str, str], ...], column_name: str
    ) -> str | None:
        normalized_column = normalize_discovery_text(column_name)
        if not normalized_column:
            return None
        for name, column_type in columns:
            if normalize_discovery_text(name) != normalized_column:
                continue
            if not any(
                token in column_type.casefold()
                for token in ("int", "float", "double", "decimal", "numeric")
            ):
                return name
        return None

    @staticmethod
    def _chart_title(topic: str, intent: AnalyticsIntent) -> str:
        suffix = " por ano" if intent.time_grain == "year" else ""
        return f"{topic.replace('_', ' ').title()}{suffix}"

    @staticmethod
    def _dataset_name(topic: str, intent: AnalyticsIntent) -> str:
        if intent.output_prefix:
            return f"{intent.output_prefix}_DATASET"
        return f"{topic.replace(' ', '_')}_dataset"

    @staticmethod
    def _saved_query_label(topic: str, intent: AnalyticsIntent) -> str:
        if intent.output_prefix:
            return f"{intent.output_prefix}_QUERY"
        return f"{topic.replace(' ', '_')}_query"

    @staticmethod
    def _display_spec(
        source: DiscoveryCandidate, title: str, time_column: str, metric: str
    ) -> ChartSpecification:
        return ChartSpecification(
            datasource_id=source.resource_id or 0,
            datasource_type="table",
            chart_title=title,
            viz_type="echarts_timeseries_bar",
            time_column=time_column,
            metric=metric,
        )

    @staticmethod
    def _viz_type(intent: AnalyticsIntent) -> str:
        if intent.chart_type == "pie":
            return "pie"
        if intent.chart_type == "area":
            return "echarts_area"
        if intent.chart_type == "line":
            return "echarts_timeseries_line"
        if intent.chart_type == "table":
            return "table"
        if intent.chart_type == "scatter":
            return "echarts_timeseries_scatter"
        if intent.chart_type == "sankey":
            return "sankey_v2"
        if intent.chart_type == "big_number":
            return "big_number_total"
        return "echarts_timeseries_bar"

    @classmethod
    def _supporting_column_effects(
        cls, columns: tuple[tuple[str, str], ...], intent: AnalyticsIntent
    ) -> list[str]:
        return [
            f"considerar coluna auxiliar `{column}`"
            for column in cls._supporting_columns(columns, intent)
        ]

    @classmethod
    def _supporting_column_findings(
        cls, columns: tuple[tuple[str, str], ...], intent: AnalyticsIntent
    ) -> list[str]:
        return [
            f"coluna auxiliar verificada: `{column}`"
            for column in cls._supporting_columns(columns, intent)
        ]

    @staticmethod
    def _supporting_columns(
        columns: tuple[tuple[str, str], ...], intent: AnalyticsIntent
    ) -> tuple[str, ...]:
        requested_terms: list[str] = []
        if intent.metric == "revenue_profit":
            requested_terms.extend(("revenue", "profit"))
        if intent.metric == "cost":
            requested_terms.extend(("cost", "revenue", "profit"))
        if intent.metric == "population":
            requested_terms.extend(("SP_POP_TOTL", "revenue", "sales"))
        if intent.metric == "cancellations":
            requested_terms.extend(("CANCELLED",))
        if intent.metric == "distance":
            requested_terms.extend(("DISTANCE",))
        if intent.dimension:
            requested_terms.extend(DIMENSION_TERM_GROUPS.get(intent.dimension, ()))
        if intent.chart_type == "sankey":
            requested_terms.extend(("region", "country"))
        if intent.chart_type == "big_number":
            requested_terms.extend(("revenue", "sales", "profit", "cost"))
        matched: list[str] = []
        for term in requested_terms:
            normalized_term = normalize_discovery_text(term)
            for name, _ in columns:
                normalized_name = normalize_discovery_text(name)
                if (
                    normalized_term
                    and (
                        normalized_term in normalized_name
                        or normalized_name in normalized_term
                    )
                    and name not in matched
                ):
                    matched.append(name)
        return tuple(matched[:6])

    @staticmethod
    def _first_dimension(columns: tuple[tuple[str, str], ...]) -> str | None:
        for name, column_type in columns:
            if not any(
                token in column_type.casefold()
                for token in ("int", "float", "double", "decimal", "numeric")
            ):
                return name
        return None

    @staticmethod
    def _aggregate_sql(
        source: DiscoveryCandidate,
        time_column: str,
        metric: str,
        intent: AnalyticsIntent,
    ) -> str:
        table = source.name
        metric_alias = "metric_value"
        if metric == "COUNT(*)":
            expression = "COUNT(*)"
        else:
            expression = metric
            metric_alias = DeterministicAnalyticsPlanner._metric_alias(metric)
        if intent.time_grain == "month":
            period_expression = f"strftime('%Y-%m', {time_column})"
            return (
                f"SELECT {period_expression} AS month, {expression} AS {metric_alias} "
                f"FROM {table} GROUP BY {period_expression}"
            )
        return (
            f"SELECT strftime('%Y', {time_column}) AS year, "
            f"{expression} AS {metric_alias} FROM {table} "
            f"GROUP BY strftime('%Y', {time_column})"
        )

    @staticmethod
    def _revenue_population_sql() -> str:
        return (
            "SELECT i.country AS country, "
            "strftime('%Y', i.transaction_date) AS year, "
            "SUM(i.revenue) AS revenue, "
            "MAX(w.SP_POP_TOTL) AS SP_POP_TOTL, "
            "SUM(i.revenue) / NULLIF(MAX(w.SP_POP_TOTL), 0) "
            "AS revenue_per_capita "
            "FROM international_sales i "
            "JOIN wb_health_population w "
            "ON lower(i.country) = lower(w.country_name) "
            "AND strftime('%Y', i.transaction_date) = CAST(w.year AS TEXT) "
            "GROUP BY i.country, strftime('%Y', i.transaction_date)"
        )

    @staticmethod
    def _sales_revenue_country_sql() -> str:
        return (
            "SELECT COALESCE(s.country, i.country) AS country, "
            "s.sales AS sales, "
            "i.revenue AS revenue "
            "FROM ("
            "SELECT country, SUM(sales) AS sales "
            "FROM cleaned_sales_data "
            "GROUP BY country"
            ") s "
            "JOIN ("
            "SELECT country, SUM(revenue) AS revenue "
            "FROM international_sales "
            "GROUP BY country"
            ") i "
            "ON lower(s.country) = lower(i.country)"
        )

    @staticmethod
    def _video_population_sql() -> str:
        return (
            "SELECT v.year AS year, "
            "v.global_sales AS global_sales, "
            "w.SP_POP_TOTL AS SP_POP_TOTL "
            "FROM ("
            "SELECT CAST(year AS TEXT) AS year, SUM(global_sales) AS global_sales "
            "FROM video_game_sales "
            "GROUP BY CAST(year AS TEXT)"
            ") v "
            "JOIN ("
            "SELECT CAST(year AS TEXT) AS year, SUM(SP_POP_TOTL) AS SP_POP_TOTL "
            "FROM wb_health_population "
            "GROUP BY CAST(year AS TEXT)"
            ") w "
            "ON v.year = w.year"
        )

    @staticmethod
    def _revenue_profit_population_sql() -> str:
        return (
            "SELECT i.region AS region, "
            "i.revenue AS revenue, "
            "i.profit AS profit, "
            "w.SP_POP_TOTL AS SP_POP_TOTL "
            "FROM ("
            "SELECT region, SUM(revenue) AS revenue, SUM(profit) AS profit "
            "FROM international_sales "
            "GROUP BY region"
            ") i "
            "LEFT JOIN ("
            "SELECT region, SUM(SP_POP_TOTL) AS SP_POP_TOTL "
            "FROM wb_health_population "
            "GROUP BY region"
            ") w "
            "ON lower(i.region) = lower(w.region)"
        )

    @staticmethod
    def _message_count_by_user_sql() -> str:
        return (
            "SELECT u.id AS user_id, "
            "u.name AS user_name, "
            "COUNT(m.ts) AS message_count "
            "FROM messages m "
            "JOIN users u ON m.user = u.id "
            "GROUP BY u.id, u.name"
        )

    @staticmethod
    def _flights_births_year_sql() -> str:
        return (
            "SELECT f.year AS year, "
            "f.flight_count AS flight_count, "
            "b.birth_count AS birth_count "
            "FROM ("
            "SELECT CAST(YEAR AS TEXT) AS year, COUNT(*) AS flight_count "
            "FROM flights "
            "GROUP BY CAST(YEAR AS TEXT)"
            ") f "
            "JOIN ("
            "SELECT strftime('%Y', ds) AS year, SUM(num) AS birth_count "
            "FROM birth_names "
            "GROUP BY strftime('%Y', ds)"
            ") b "
            "ON f.year = b.year"
        )

    @staticmethod
    def _aggregate_time_alias(intent: AnalyticsIntent) -> str:
        return "month" if intent.time_grain == "month" else "year"

    @staticmethod
    def _chart_time_grain(
        time_column: str, intent: AnalyticsIntent
    ) -> str | None:
        if normalize_discovery_text(time_column) in {"year", "month", "period"}:
            return None
        if intent.time_grain is None:
            return None
        return "P1M" if intent.time_grain == "month" else "P1Y"

    @staticmethod
    def _metric_alias(metric: str) -> str:
        if metric == "COUNT(*)":
            return "metric_value"
        return metric.lower().replace("(", "_").replace(")", "")

    def _validate_action(self, action: PlannedAction) -> None:
        tool = self.registry.get(action.tool_name)
        if tool is None or not tool.requires_confirmation:
            raise AnalyticsPlanValidationError(
                f"Ação planejada indisponível: {action.tool_name}"
            )
        if tool not in self.registry.tools_for_user(self.user):
            raise AnalyticsPlanValidationError(
                f"Você não possui permissão para a ação: {action.tool_name}"
            )
        if self._contains_reference(action.params):
            return
        if error := getattr(tool, "validate_params", lambda _: None)(action.params):
            raise AnalyticsPlanValidationError(error)

    @classmethod
    def _contains_reference(cls, value: Any) -> bool:
        if isinstance(value, dict) and set(value) == {"$ref"}:
            return True
        if isinstance(value, dict):
            return any(cls._contains_reference(item) for item in value.values())
        if isinstance(value, list):
            return any(cls._contains_reference(item) for item in value)
        return False

    def _dashboard_action(
        self, dashboard_name: str, chart_action_index: int
    ) -> tuple[list[PlannedAction], list[str]]:
        """Reuse an accessible dashboard or plan its creation before publication."""
        dashboard_id = self._find_dashboard_id(dashboard_name)
        actions: list[PlannedAction] = []
        effects: list[str] = []
        if dashboard_id is None:
            suggestions = self._dashboard_suggestions(dashboard_name)
            options = "\n".join(
                f"{index}. `{dashboard.dashboard_title}`"
                for index, dashboard in enumerate(suggestions, start=1)
            )
            message = f"Não encontrei o dashboard `{dashboard_name}`."
            if options:
                message += f"\nQual dashboard deseja usar?\n{options}"
            else:
                message += "\nNão encontrei dashboards acessíveis parecidos."
            raise DashboardSelectionRequired(message)
        else:
            dashboard_value = dashboard_id
            effects.append(f"reutilizar o dashboard `{dashboard_name}`")
        actions.append(
            PlannedAction(
                "add_chart_to_dashboard",
                {
                    "chart_id": {"$ref": f"actions.{chart_action_index}.id"},
                    "dashboard_id": dashboard_value,
                },
            )
        )
        effects.append(f"publicar o gráfico no dashboard `{dashboard_name}`")
        return actions, effects

    def _find_dashboard_id(self, dashboard_name: str) -> int | None:
        from superset.extensions import db, security_manager
        from superset.models.dashboard import Dashboard

        normalized = self._normalize(dashboard_name)
        matches = []
        for dashboard in db.session.query(Dashboard).all():
            title = self._normalize(dashboard.dashboard_title)
            slug = self._normalize(str(dashboard.slug or ""))
            title_matches = title == normalized or self._compact(title) == self._compact(
                normalized
            )
            slug_matches = slug == normalized or self._compact(slug) == self._compact(
                normalized
            )
            if (
                title_matches or slug_matches
            ) and security_manager.can_access_dashboard(dashboard):
                matches.append(dashboard)
        if len(matches) > 1:
            raise AnalyticsPlanValidationError(
                f"Mais de um dashboard corresponde a `{dashboard_name}`"
            )
        if matches:
            return matches[0].id
        return None

    def _dashboard_suggestions(self, dashboard_name: str) -> list[Any]:
        from superset.extensions import db, security_manager
        from superset.models.dashboard import Dashboard

        normalized = self._normalize(dashboard_name)
        scored = []
        for dashboard in db.session.query(Dashboard).all():
            if not security_manager.can_access_dashboard(dashboard):
                continue
            names = (
                str(dashboard.dashboard_title or ""),
                str(dashboard.slug or ""),
            )
            score = max(
                self._dashboard_similarity(normalized, self._normalize(name))
                for name in names
            )
            if score >= 0.45:
                scored.append((score, dashboard.dashboard_title.casefold(), dashboard))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [dashboard for _, __, dashboard in scored[:3]]

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
        return slug or "ai-dashboard"

    @staticmethod
    def _normalize(value: str) -> str:
        return normalize_discovery_text(value)

    @staticmethod
    def _compact(value: str) -> str:
        return re.sub(r"\s+", "", value)

    @staticmethod
    def _dashboard_similarity(requested: str, candidate: str) -> float:
        if not requested or not candidate:
            return 0.0
        if requested in candidate or candidate in requested:
            return 1.0
        return SequenceMatcher(None, requested, candidate).ratio()
