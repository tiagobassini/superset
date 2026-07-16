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

from superset.ai.chart_spec import ChartSpecification
from superset.ai.execution_plan import ExecutionPlanService, PlannedAction
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


class WriteTool(AITool):
    """A validated write operation with configurable deterministic result."""

    description = "test write"
    parameters_schema = {"type": "object", "properties": {}}
    requires_confirmation = True

    def __init__(self, name: str, result: ToolResult) -> None:
        self.name = name
        self.result = result
        self.calls = 0

    def execute(self, user, params):
        self.calls += 1
        return self.result


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
