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
from superset.ai.discovery import classify_columns, DiscoveryCandidate
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
        if source.resource_type != "dataset" or source.resource_id is None:
            raise AnalyticsPlanValidationError(
                "A fonte selecionada ainda precisa ser materializada como dataset"
            )
        column_groups = classify_columns(
            [
                {"name": name, "type": column_type}
                for name, column_type in source.columns
            ]
        )
        time_column = self._time_column(column_groups, intent)
        metric = self._metric(column_groups, intent)
        topic = intent.topic or source.name
        chart_specification = ChartSpecification(
            datasource_id=source.resource_id,
            datasource_type="table",
            chart_title=self._chart_title(topic, intent),
            viz_type="echarts_timeseries_bar",
            time_column=time_column,
            metric=metric,
        )
        chart_spec_payload = asdict(chart_specification)
        chart_spec_payload["group_by"] = list(chart_specification.group_by)
        actions = [
            PlannedAction("create_chart", {"chart_spec": chart_spec_payload})
        ]
        for action in actions:
            self._validate_action(action)
        effects = [
            f"criar o gráfico de barras `{chart_specification.chart_title}`",
            f"usar `{time_column}` como dimensão temporal e `{metric}` como métrica",
        ]
        if intent.goal is AnalyticsGoal.PUBLISH_CHART and intent.target_dashboard:
            dashboard_action, dashboard_effect = self._dashboard_action(
                intent.target_dashboard, chart_action_index=0
            )
            actions.extend(dashboard_action)
            for action in dashboard_action:
                self._validate_action(action)
            effects.extend(dashboard_effect)
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
                f"coluna temporal verificada: `{time_column}`",
                f"métrica compatível: `{metric}`",
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
    def _metric(groups: dict[str, list[str]], intent: AnalyticsIntent) -> str:
        if intent.metric == "count":
            return "COUNT(*)"
        if groups["measures"]:
            return f"SUM({groups['measures'][0]})"
        if groups["identifiers"]:
            return f"COUNT({groups['identifiers'][0]})"
        raise AnalyticsPlanValidationError(
            "A fonte não possui medida ou identificador verificável"
        )

    @staticmethod
    def _chart_title(topic: str, intent: AnalyticsIntent) -> str:
        suffix = " por ano" if intent.time_grain == "year" else ""
        return f"{topic.replace('_', ' ').title()}{suffix}"

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
        if error := getattr(tool, "validate_params", lambda _: None)(action.params):
            raise AnalyticsPlanValidationError(error)

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
        for dashboard in db.session.query(Dashboard).all():
            if (
                self._normalize(dashboard.dashboard_title) == normalized
                and security_manager.can_access_dashboard(dashboard)
            ):
                return dashboard.id
        return None

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
        return slug or "ai-dashboard"

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().replace("_", " ").split())
