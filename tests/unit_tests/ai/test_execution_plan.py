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
"""Tests for typed chart payloads and idempotent write plans."""

from types import SimpleNamespace

import pytest

from superset.ai.analytics_execution import (
    AnalyticsPlanValidationError,
    DeterministicAnalyticsPlanner,
)
from superset.ai.chart_spec import ChartSpecification
from superset.ai.discovery import DiscoveryCandidate
from superset.ai.execution_plan import ExecutionPlanService, PlannedAction
from superset.ai.planner import AnalyticsGoal, AnalyticsIntent
from superset.ai.tools.base import AITool, ToolResult
from superset.ai.tools.registry import ToolRegistry


class Cache:
    """Small in-memory cache used to exercise plan state transitions."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, timeout: int) -> None:
        self.values[key] = value

    def add(self, key: str, value: object, timeout: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class WriteTool(AITool):
    """A validated write operation with configurable deterministic result."""

    description = "test write"
    parameters_schema = {"type": "object", "properties": {}}
    requires_confirmation = True

    def __init__(self, name: str, result: ToolResult) -> None:
        self.name = name
        self.result = result
        self.calls = 0
        self.params: list[dict[str, object]] = []

    def execute(self, user, params):
        self.calls += 1
        self.params.append(params)
        return self.result


def _dataset_source(columns: tuple[tuple[str, str], ...]) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        resource_type="dataset",
        resource_id=7,
        name="international_sales",
        database_id=1,
        database_name="Examples",
        schema="public",
        columns=columns,
        source_key="source:1:public:international_sales",
    )


def test_deterministic_planner_builds_valid_chart_plan_from_verified_dataset() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("create_chart", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_CHART,
        topic="vendas",
        metric="count",
        time_grain="year",
    )

    plan = DeterministicAnalyticsPlanner(
        registry, SimpleNamespace(id=4), "agent-1"
    ).build(
        _dataset_source(
            (("order_date", "DATE"), ("sale_id", "INTEGER"), ("amount", "NUMERIC"))
        ),
        intent,
    )

    assert plan.execution_plan.user_id == 4
    assert plan.execution_plan.actions[0].tool_name == "create_chart"
    assert plan.chart_specification.datasource_id == 7
    assert plan.chart_specification.time_column == "order_date"
    assert plan.chart_specification.metric == "COUNT(*)"
    assert "Nenhum recurso foi criado" in plan.to_chat_text()


def test_deterministic_planner_rejects_annual_chart_without_verified_time() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("create_chart", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_CHART,
        topic="vendas",
        metric="count",
        time_grain="year",
    )

    with pytest.raises(AnalyticsPlanValidationError, match="temporal"):
        DeterministicAnalyticsPlanner(
            registry, SimpleNamespace(id=4), "agent-1"
        ).build(_dataset_source((("amount", "NUMERIC"),)), intent)


def test_deterministic_planner_reuses_dashboard_with_dependent_publish_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    for name in ("create_chart", "add_chart_to_dashboard"):
        registry.register(WriteTool(name, ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.PUBLISH_CHART,
        topic="vendas",
        target_dashboard="CBMES",
        metric="count",
        time_grain="year",
    )
    planner = DeterministicAnalyticsPlanner(registry, SimpleNamespace(id=4), "agent-1")
    monkeypatch.setattr(planner, "_find_dashboard_id", lambda _: 9)

    plan = planner.build(
        _dataset_source((("order_date", "DATE"), ("amount", "NUMERIC"))), intent
    )

    assert [action.tool_name for action in plan.execution_plan.actions] == [
        "create_chart",
        "add_chart_to_dashboard",
    ]
    assert plan.execution_plan.actions[1].params == {
        "chart_id": {"$ref": "actions.0.id"},
        "dashboard_id": 9,
    }


def test_execution_plan_resolves_a_prior_action_id_before_execution() -> None:
    registry = ToolRegistry()
    chart = WriteTool("create_chart", ToolResult(True, {"id": 12}))
    publish = WriteTool("add_chart_to_dashboard", ToolResult(True, {"id": 9}))
    registry.register(chart)
    registry.register(publish)
    service = ExecutionPlanService(
        registry, SimpleNamespace(id=4), "agent-1", Cache()
    )
    plan = service.create(
        [
            PlannedAction(
                "create_chart",
                {
                    "chart_spec": {
                        "datasource_id": 7,
                        "datasource_type": "table",
                        "chart_title": "Vendas por ano",
                        "viz_type": "echarts_timeseries_bar",
                        "time_column": "order_date",
                        "metric": "COUNT(*)",
                    }
                },
            ),
            PlannedAction(
                "add_chart_to_dashboard",
                {"chart_id": {"$ref": "actions.0.id"}, "dashboard_id": 9},
            ),
        ]
    )

    service.confirm_and_execute(plan.id)

    assert publish.params == [{"chart_id": 12, "dashboard_id": 9}]


def test_chart_spec_requires_source_time_and_metric_and_builds_payload() -> None:
    spec = ChartSpecification.from_dict(
        {
            "datasource_id": 7,
            "datasource_type": "table",
            "chart_title": "Pedidos por ano",
            "viz_type": "echarts_timeseries_line",
            "time_column": "order_date",
            "metric": "COUNT(order_id)",
        }
    )

    payload = spec.to_chart_payload()

    assert payload["slice_name"] == "Pedidos por ano"
    assert '"granularity_sqla": "order_date"' in payload["params"]
    with pytest.raises(ValueError, match="time_column"):
        ChartSpecification.from_dict({"datasource_id": 7})


def test_execution_plan_executes_once_and_returns_cached_result() -> None:
    registry = ToolRegistry()
    tool = WriteTool("create_dataset", ToolResult(True, {"id": 1}))
    registry.register(tool)
    service = ExecutionPlanService(
        registry, SimpleNamespace(id=4), "agent-1", Cache()
    )
    plan = service.create([PlannedAction("create_dataset", {"table_name": "sales"})])

    assert service.confirm_and_execute(plan.id) == [ToolResult(True, {"id": 1})]
    assert service.confirm_and_execute(plan.id) == [ToolResult(True, {"id": 1})]
    assert tool.calls == 1


def test_execution_plan_stops_after_first_failed_step() -> None:
    registry = ToolRegistry()
    first = WriteTool("create_dataset", ToolResult(False, None, "invalid table"))
    second = WriteTool("create_chart", ToolResult(True, {"id": 2}))
    registry.register(first)
    registry.register(second)
    service = ExecutionPlanService(
        registry, SimpleNamespace(id=4), "agent-1", Cache()
    )
    plan = service.create(
        [
            PlannedAction("create_dataset", {"table_name": "sales"}),
            PlannedAction("create_chart", {"params": "{}"}),
        ]
    )

    results = service.confirm_and_execute(plan.id)

    assert results == [ToolResult(False, None, "invalid table")]
    assert first.calls == 1
    assert second.calls == 0


def test_execution_plan_revalidates_tool_access_and_rejects_active_duplicate() -> None:
    registry = ToolRegistry()
    tool = WriteTool("create_dataset", ToolResult(True, {"id": 1}))
    registry.register(tool)
    cache = Cache()
    service = ExecutionPlanService(registry, SimpleNamespace(id=4), "agent-1", cache)
    plan = service.create([PlannedAction("create_dataset", {"table_name": "sales"})])
    cache.add(service._lock_key(plan.id), True, timeout=600)

    with pytest.raises(Exception, match="already executing"):
        service.confirm_and_execute(plan.id)
    assert tool.calls == 0
