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

import re
from dataclasses import asdict, dataclass
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
                source, actions, effects, chart_specification, "COUNT(*)"
            )
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
                source, actions, effects, chart_specification, metric
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
                    source, actions, effects, chart_specification, metric
                )
        else:
            datasource_id = int(source.resource_id)

        chart_title = intent.chart_title or self._chart_title(topic, intent)
        chart_specification = ChartSpecification(
            datasource_id=int(source.resource_id) if isinstance(datasource_id, int) else 0,
            datasource_type="table",
            chart_title=chart_title,
            viz_type="echarts_timeseries_bar",
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
            f"criar o gráfico de barras `{chart_specification.chart_title}`",
            f"usar `{chart_time_column}` como dimensão temporal e "
            f"`{chart_metric}` como métrica",
        ]
        if group_by:
            effects.append(f"agrupar por `{group_by}`")
        if intent.goal is AnalyticsGoal.PUBLISH_CHART and intent.target_dashboard:
            dashboard_action, dashboard_effect = self._dashboard_action(
                intent.target_dashboard, chart_action_index=chart_action_index
            )
            actions.extend(dashboard_action)
            effects.extend(dashboard_effect)
        return self._finalize(source, actions, effects, chart_specification, metric)

    def _finalize(
        self,
        source: DiscoveryCandidate,
        actions: list[PlannedAction],
        effects: list[str],
        chart_specification: ChartSpecification,
        metric: str,
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
                f"coluna temporal verificada: `{chart_specification.time_column}`",
                f"métrica compatível: `{metric}`",
                *(
                    f"dimensão compatível: `{dimension}`"
                    for dimension in chart_specification.group_by
                ),
            ),
            effects=tuple(effects),
            chart_specification=chart_specification,
        )

    @staticmethod
    def _time_column(groups: dict[str, list[str]], intent: AnalyticsIntent) -> str:
        if intent.time_grain == "year" and not groups["temporal"]:
            raise AnalyticsPlanValidationError(
                "A fonte não possui uma coluna temporal para a análise anual"
            )
        if groups["temporal"]:
            return groups["temporal"][0]
        raise AnalyticsPlanValidationError(
            "A fonte não possui uma coluna temporal verificável"
        )

    @staticmethod
    def _metric(
        groups: dict[str, list[str]],
        intent: AnalyticsIntent,
        columns: tuple[tuple[str, str], ...],
    ) -> str:
        if intent.metric == "count":
            return "COUNT(*)"
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
    def _aggregate_time_alias(intent: AnalyticsIntent) -> str:
        return "month" if intent.time_grain == "month" else "year"

    @staticmethod
    def _chart_time_grain(
        time_column: str, intent: AnalyticsIntent
    ) -> str | None:
        if normalize_discovery_text(time_column) in {"year", "month", "period"}:
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
            create_index = chart_action_index + 1
            actions.append(
                PlannedAction(
                    "create_dashboard",
                    {
                        "dashboard_title": dashboard_name,
                        "slug": self._slug(dashboard_name),
                    },
                )
            )
            dashboard_value: int | dict[str, str] = {
                "$ref": f"actions.{create_index}.id"
            }
            effects.append(f"criar o dashboard `{dashboard_name}`")
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
            title_matches = self._normalize(dashboard.dashboard_title) == normalized
            slug_matches = self._normalize(str(dashboard.slug or "")) == normalized
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

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
        return slug or "ai-dashboard"

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().replace("_", " ").split())
