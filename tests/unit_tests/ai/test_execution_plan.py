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
from superset.utils import json


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


def test_deterministic_planner_uses_requested_metric_column() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("create_chart", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_CHART,
        topic="receita",
        metric="revenue",
        time_grain="year",
    )

    plan = DeterministicAnalyticsPlanner(
        registry, SimpleNamespace(id=4), "agent-1"
    ).build(
        _dataset_source(
            (
                ("transaction_date", "DATE"),
                ("quantity", "INTEGER"),
                ("revenue", "NUMERIC"),
                ("profit", "NUMERIC"),
            )
        ),
        intent,
    )

    assert plan.chart_specification.metric == "SUM(revenue)"


def test_deterministic_planner_uses_requested_grouping_dimension() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("create_chart", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_CHART,
        topic="quantidade",
        metric="quantity",
        dimension="product_category",
        time_grain="year",
    )

    plan = DeterministicAnalyticsPlanner(
        registry, SimpleNamespace(id=4), "agent-1"
    ).build(
        _dataset_source(
            (
                ("transaction_date", "DATE"),
                ("product_category", "VARCHAR"),
                ("quantity", "INTEGER"),
            )
        ),
        intent,
    )

    assert plan.chart_specification.group_by == ("product_category",)
    assert plan.execution_plan.actions[0].params["chart_spec"]["group_by"] == [
        "product_category"
    ]
    assert "dimensão compatível: `product_category`" in plan.findings


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
        DeterministicAnalyticsPlanner(registry, SimpleNamespace(id=4), "agent-1").build(
            _dataset_source((("amount", "NUMERIC"),)), intent
        )


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


def test_deterministic_planner_preserves_requested_chart_title() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("create_chart", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_CHART,
        topic="receita",
        chart_title="ai_test_p11",
        metric="revenue",
        time_grain="year",
    )

    plan = DeterministicAnalyticsPlanner(
        registry, SimpleNamespace(id=4), "agent-1"
    ).build(
        _dataset_source((("transaction_date", "DATE"), ("revenue", "NUMERIC"))),
        intent,
    )

    chart_spec = plan.execution_plan.actions[0].params["chart_spec"]
    assert chart_spec["chart_title"] == "ai_test_p11"
    assert plan.chart_specification.chart_title == "ai_test_p11"


def test_deterministic_planner_chains_dataset_chart_and_dashboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    for name in ("create_dataset", "create_chart", "add_chart_to_dashboard"):
        registry.register(WriteTool(name, ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.PUBLISH_CHART,
        topic="vendas",
        target_dashboard="CBMES",
        chart_title="ai_test_p50_chart",
        dataset_name="ai_test_p50_dataset",
        output_prefix="ai_test_p50",
        metric="revenue",
        time_grain="year",
    )
    planner = DeterministicAnalyticsPlanner(registry, SimpleNamespace(id=4), "agent-1")
    monkeypatch.setattr(planner, "_find_dashboard_id", lambda _: 9)

    plan = planner.build(
        _dataset_source((("transaction_date", "DATE"), ("revenue", "NUMERIC"))),
        intent,
    )

    assert [action.tool_name for action in plan.execution_plan.actions] == [
        "create_dataset",
        "create_chart",
        "add_chart_to_dashboard",
    ]
    assert plan.execution_plan.actions[0].params["table_name"] == "ai_test_p50_dataset"
    assert plan.execution_plan.actions[0].params["overwrite"] is True
    assert "strftime('%Y', transaction_date) AS year" in (
        plan.execution_plan.actions[0].params["sql"]
    )
    assert plan.execution_plan.actions[1].params["chart_spec"] == {
        "datasource_id": {"$ref": "actions.0.id"},
        "datasource_type": "table",
        "chart_title": "ai_test_p50_chart",
        "viz_type": "echarts_timeseries_bar",
        "time_column": "year",
        "metric": "SUM(sum_revenue)",
        "time_grain": None,
        "group_by": [],
    }
    assert plan.execution_plan.actions[1].params["overwrite"] is True
    assert plan.execution_plan.actions[2].params == {
        "chart_id": {"$ref": "actions.1.id"},
        "dashboard_id": 9,
    }


def test_deterministic_planner_creates_dataset_from_saved_query() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("create_dataset", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_DATASET,
        topic="vendas",
        dataset_name="ai_test_p20",
        metric="sales",
        time_grain="year",
    )
    source = DiscoveryCandidate(
        resource_type="saved_query",
        resource_id=19,
        name="ai_test_p19",
        database_id=1,
        database_name="Examples",
        schema="main",
        columns=(("period", "DATE"), ("sales", "NUMERIC")),
        source_key="saved_query:19",
    )

    plan = DeterministicAnalyticsPlanner(
        registry, SimpleNamespace(id=4), "agent-1"
    ).build(source, intent)

    assert plan.execution_plan.actions == (
        PlannedAction(
            "create_dataset",
            {"table_name": "ai_test_p20", "saved_query_id": 19, "overwrite": True},
        ),
    )


def test_deterministic_planner_builds_saved_query_plan() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("save_sql_query", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_QUERY,
        topic="populacao",
        saved_query_label="ai_test_p44",
        metric="population",
        time_grain="year",
    )

    plan = DeterministicAnalyticsPlanner(
        registry, SimpleNamespace(id=4), "agent-1"
    ).build(
        _dataset_source((("year", "INTEGER"), ("SP_POP_TOTL", "NUMERIC"))),
        intent,
    )

    assert plan.execution_plan.actions[0].tool_name == "save_sql_query"
    assert plan.execution_plan.actions[0].params["label"] == "ai_test_p44"
    assert plan.execution_plan.actions[0].params["overwrite"] is True
    assert "SUM(SP_POP_TOTL)" in plan.execution_plan.actions[0].params["sql"]


def test_deterministic_planner_builds_monthly_saved_query_plan() -> None:
    registry = ToolRegistry()
    registry.register(WriteTool("save_sql_query", ToolResult(True, {"id": 1})))
    intent = AnalyticsIntent(
        goal=AnalyticsGoal.CREATE_QUERY,
        topic="vendas",
        saved_query_label="ai_test_p19",
        metric="sales",
        time_grain="month",
    )

    plan = DeterministicAnalyticsPlanner(
        registry, SimpleNamespace(id=4), "agent-1"
    ).build(
        DiscoveryCandidate(
            resource_type="dataset",
            resource_id=9,
            name="cleaned_sales_data",
            database_id=1,
            database_name="Examples",
            schema="main",
            columns=(("order_date", "DATE"), ("sales", "NUMERIC")),
            source_key="source:1:main:cleaned_sales_data",
        ),
        intent,
    )

    sql = plan.execution_plan.actions[0].params["sql"]
    assert plan.execution_plan.actions[0].params["label"] == "ai_test_p19"
    assert " AS month" in sql
    assert "SUM(sales)" in sql


def test_execution_plan_resolves_a_prior_action_id_before_execution() -> None:
    registry = ToolRegistry()
    chart = WriteTool("create_chart", ToolResult(True, {"id": 12}))
    publish = WriteTool("add_chart_to_dashboard", ToolResult(True, {"id": 9}))
    registry.register(chart)
    registry.register(publish)
    service = ExecutionPlanService(registry, SimpleNamespace(id=4), "agent-1", Cache())
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
    assert json.loads(payload["params"])["metrics"] == [
        {
            "expressionType": "SIMPLE",
            "column": {"column_name": "order_id", "type": "NUMERIC"},
            "aggregate": "COUNT",
            "label": "COUNT(order_id)",
        }
    ]
    with pytest.raises(ValueError, match="time_column"):
        ChartSpecification.from_dict({"datasource_id": 7})


def test_chart_spec_allows_empty_time_grain_for_preaggregated_periods() -> None:
    spec = ChartSpecification.from_dict(
        {
            "datasource_id": 22,
            "datasource_type": "table",
            "chart_title": "AI_TEST_P18",
            "viz_type": "echarts_timeseries_bar",
            "time_column": "year",
            "metric": "SUM(sum_revenue)",
            "time_grain": None,
        }
    )

    form_data = json.loads(spec.to_chart_payload()["params"])

    assert form_data["granularity_sqla"] == "year"
    assert form_data["time_grain_sqla"] is None


def test_chart_spec_rejects_a_metric_column_absent_from_verified_schema() -> None:
    spec = ChartSpecification.from_dict(
        {
            "datasource_id": 7,
            "datasource_type": "table",
            "chart_title": "Sales",
            "viz_type": "echarts_timeseries_bar",
            "time_column": "order_date",
            "metric": "SUM(na_sales)",
        }
    )

    with pytest.raises(ValueError, match="metric column does not exist"):
        spec.validate_columns((("order_date", "DATE"), ("sales", "NUMERIC")))


def test_execution_plan_executes_once_and_returns_cached_result() -> None:
    registry = ToolRegistry()
    tool = WriteTool("create_dataset", ToolResult(True, {"id": 1}))
    registry.register(tool)
    service = ExecutionPlanService(registry, SimpleNamespace(id=4), "agent-1", Cache())
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
    service = ExecutionPlanService(registry, SimpleNamespace(id=4), "agent-1", Cache())
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
