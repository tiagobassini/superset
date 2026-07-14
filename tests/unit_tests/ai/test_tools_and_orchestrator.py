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
"""Unit tests for the AI tool registry and orchestration safety boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from superset.ai.orchestrator import AIOrchestrator
from superset.ai.providers.base import ProviderResponse, ToolCall
from superset.ai.tools.base import AITool, ToolResult
from superset.ai.tools.registry import ToolRegistry, create_default_registry


class StubTool(AITool):
    """A deterministic tool used to test the registry and orchestrator."""

    name = "lookup"
    description = "Look up a value"
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, requires_confirmation: bool = False) -> None:
        self.requires_confirmation = requires_confirmation
        self.calls: list[dict[str, Any]] = []

    def execute(self, user: Any, params: dict[str, Any]) -> ToolResult:
        self.calls.append(params)
        return ToolResult(True, {"value": params["value"]})


class StubProvider:
    """Return scripted provider responses without contacting a real API."""

    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses
        self.messages: list[list[dict[str, Any]]] = []

    def chat_with_tools(self, messages, tools, model):
        self.messages.append(messages)
        return self.responses.pop(0)

    @staticmethod
    def build_tool_message(tool_call_id: str, result_json: str) -> dict[str, str]:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result_json}


class StubCache:
    """In-memory cache implementing the small API used by the orchestrator."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def set(self, key: str, value: Any, timeout: int) -> None:
        self.values[key] = value

    def get(self, key: str) -> Any:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def test_default_registry_contains_all_mvp_tools() -> None:
    registry = create_default_registry()
    assert set(registry._tools) == {
        "add_chart_to_dashboard",
        "create_chart",
        "create_dashboard",
        "create_dataset",
        "edit_chart",
        "edit_dashboard",
        "get_current_context",
        "get_dataset_schema",
        "get_table_schema",
        "list_charts",
        "list_dashboards",
        "list_database_tables",
        "list_databases",
        "list_datasets",
        "list_saved_queries",
        "run_sql_query",
        "save_sql_query",
    }


def test_registry_rejects_duplicate_tool_names() -> None:
    registry = ToolRegistry()
    registry.register(StubTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(StubTool())


def test_orchestrator_executes_read_tool_and_continues_to_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    tool = StubTool()
    registry.register(tool)
    provider = StubProvider(
        [
            ProviderResponse(
                "",
                [ToolCall("call_1", "lookup", {"value": "sales"})],
            ),
            ProviderResponse("Sales dataset found."),
        ]
    )
    monkeypatch.setattr(AIOrchestrator, "_build_provider", staticmethod(lambda _: provider))
    agent = SimpleNamespace(provider="openai", model="test", api_key_encrypted=None)
    user = SimpleNamespace(id=42)

    result = AIOrchestrator(agent, registry, user).chat("Find sales", [], {"page": "sql"})

    assert result.response == "Sales dataset found."
    assert result.pending_actions == []
    assert tool.calls == [{"value": "sales"}]
    assert provider.messages[1][-1]["role"] == "tool"


def test_orchestrator_defers_write_tool_until_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    tool = StubTool(requires_confirmation=True)
    registry.register(tool)
    provider = StubProvider(
        [ProviderResponse("I can do that.", [ToolCall("call_1", "lookup", {"value": "x"})])]
    )
    cache = StubCache()
    monkeypatch.setattr(AIOrchestrator, "_build_provider", staticmethod(lambda _: provider))
    agent = SimpleNamespace(provider="openai", model="test", api_key_encrypted=None)
    user = SimpleNamespace(id=42)
    orchestrator = AIOrchestrator(agent, registry, user, cache=cache)

    result = orchestrator.chat("Change it", [], {"page": "dashboard"})

    assert tool.calls == []
    action = result.pending_actions[0]
    assert action.type == "lookup"
    assert orchestrator.confirm_and_execute(action.id).data == {"value": "x"}
    assert tool.calls == [{"value": "x"}]
