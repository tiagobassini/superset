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

from superset.ai.discovery import (
    DiscoveryCandidate,
    DiscoveryResult,
)
from superset.ai.orchestrator import AIOrchestrator
from superset.ai.planner import AnalyticsTaskPlanner
from superset.ai.providers.base import ProviderResponse, ToolCall
from superset.ai.tools.base import AITool, ToolResult
from superset.ai.tools.builtin import BuiltinTool
from superset.ai.tools.registry import create_default_registry, ToolRegistry


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
        self.tools: list[list[dict[str, Any]]] = []

    def chat_with_tools(self, messages, tools, model):
        self.messages.append(messages)
        self.tools.append(tools)
        return self.responses.pop(0)

    @staticmethod
    def expand_discovery_terms(_: str, __: str, ___: str) -> list[str]:
        return []

    @staticmethod
    def build_assistant_message(content, tool_calls):
        return {"role": "assistant", "content": content, "tool_calls": tool_calls}

    @staticmethod
    def build_tool_message(tool_call_id: str, result_json: str) -> dict[str, str]:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result_json}


class StubCache:
    """In-memory cache implementing the small API used by the orchestrator."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.timeouts: dict[str, int] = {}

    def set(self, key: str, value: Any, timeout: int) -> None:
        self.values[key] = value
        self.timeouts[key] = timeout

    def get(self, key: str) -> Any:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _discovery_candidate(name: str, score: int, resource_id: int) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        resource_type="dataset",
        resource_id=resource_id,
        name=name,
        database_id=1,
        database_name="Examples",
        schema="public",
        columns=(("order_date", "DATE"), ("amount", "NUMERIC")),
        source_key=f"source:{resource_id}",
        score=score,
        reasons=("nome relacionado ao tema", "coluna temporal: order_date"),
    )


def _patch_discovery(
    monkeypatch: pytest.MonkeyPatch, candidates: tuple[DiscoveryCandidate, ...]
) -> list[object]:
    calls: list[object] = []

    class StubDiscoveryService:
        def __init__(self, user: object) -> None:
            self.user = user

        def discover(self, query, intent, context):
            calls.append(self.user)
            return DiscoveryResult(query, candidates, {"datasets": len(candidates)})

        @staticmethod
        def revalidate_candidate(candidate: DiscoveryCandidate) -> DiscoveryCandidate:
            return candidate

    monkeypatch.setattr(
        "superset.ai.orchestrator.AnalyticsDiscoveryService", StubDiscoveryService
    )
    return calls


def _planning_registry() -> ToolRegistry:
    registry = ToolRegistry()
    chart_tool = StubTool(requires_confirmation=True)
    chart_tool.name = "create_chart"
    registry.register(chart_tool)
    return registry


def test_orchestrator_proposes_concrete_sources_when_discovery_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (
        _discovery_candidate("international_sales", 40, 11),
        _discovery_candidate("sales_history", 36, 12),
    )
    _patch_discovery(monkeypatch, candidates)
    provider = StubProvider([])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    cache = StubCache()
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )
    orchestrator = AIOrchestrator(
        agent, _planning_registry(), SimpleNamespace(id=42), cache
    )

    result = orchestrator.chat(
        "Crie um gráfico de vendas por ano", [], {"page": "home"}
    )

    assert "1. Dataset `international_sales`" in result.response
    assert "2. Dataset `sales_history`" in result.response
    assert result.response.endswith("ID?")
    assert provider.messages == []
    assert cache.get(orchestrator._discovery_selection_key()) is not None


def test_orchestrator_resumes_ambiguous_discovery_by_index_without_researching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (
        _discovery_candidate("international_sales", 40, 11),
        _discovery_candidate("sales_history", 36, 12),
    )
    discovery_calls = _patch_discovery(monkeypatch, candidates)
    provider = StubProvider([])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    cache = StubCache()
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )
    orchestrator = AIOrchestrator(
        agent, _planning_registry(), SimpleNamespace(id=42), cache
    )

    orchestrator.chat("Crie um gráfico de vendas por ano", [], {"page": "home"})
    result = orchestrator.chat("2", [], {"page": "home"})

    assert len(discovery_calls) == 1
    assert "Plano de análise pronto" in result.response
    assert "sales_history" in result.response
    assert provider.messages == []
    assert cache.get(orchestrator._discovery_selection_key()) is None


@pytest.mark.parametrize(
    ("selection", "expected_name"),
    [("international_sales", "international_sales"), ("dataset 12", "sales_history")],
)
def test_orchestrator_resolves_discovery_choice_by_name_or_reference(
    monkeypatch: pytest.MonkeyPatch, selection: str, expected_name: str
) -> None:
    provider = StubProvider([])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    cache = StubCache()
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )
    orchestrator = AIOrchestrator(agent, ToolRegistry(), SimpleNamespace(id=42), cache)
    orchestrator._store_discovery_selection(
        "Crie um gráfico de vendas por ano",
        (
            _discovery_candidate("international_sales", 40, 11),
            _discovery_candidate("sales_history", 36, 12),
        ),
    )

    resolved = orchestrator._resolve_discovery_selection(selection)

    assert resolved is not None
    assert resolved["name"] == expected_name
    assert cache.get(orchestrator._discovery_selection_key()) is None


def test_orchestrator_uses_a_clear_discovery_winner_without_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_discovery(
        monkeypatch,
        (
            _discovery_candidate("international_sales", 45, 11),
            _discovery_candidate("sales_history", 30, 12),
        ),
    )
    provider = StubProvider([])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )

    orchestrator = AIOrchestrator(
        agent, _planning_registry(), SimpleNamespace(id=42), StubCache()
    )
    result = orchestrator.chat(
        "Crie um gráfico de vendas por ano", [], {"page": "home"}
    )

    assert "Plano de análise pronto" in result.response
    assert "international_sales" in result.response
    assert provider.messages == []


def test_orchestrator_answers_read_only_prompt_with_explicit_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_discovery(
        monkeypatch,
        (
            DiscoveryCandidate(
                resource_type="dataset",
                resource_id=11,
                name="international_sales",
                database_id=1,
                database_name="Examples",
                schema="main",
                columns=(
                    ("transaction_date", "DATE"),
                    ("region", "VARCHAR"),
                    ("revenue", "NUMERIC"),
                ),
                source_key="source:11",
                score=45,
            ),
        ),
    )
    provider = StubProvider([])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )

    result = AIOrchestrator(
        agent, ToolRegistry(), SimpleNamespace(id=42), StubCache()
    ).chat(
        "Use o dataset international_sales e mostre a receita por região.",
        [],
        {"page": "home"},
    )

    assert "Fonte selecionada" in result.response
    assert "international_sales" in result.response
    assert "region" in result.response
    assert "revenue" in result.response
    assert provider.messages == []


def test_orchestrator_explains_when_discovery_finds_no_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_discovery(monkeypatch, ())
    provider = StubProvider([])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )

    result = AIOrchestrator(
        agent, ToolRegistry(), SimpleNamespace(id=42), StubCache()
    ).chat("Crie um gráfico de vendas por ano", [], {"page": "home"})

    assert "Não encontrei fontes" in result.response
    assert "qual é a tabela" not in result.response.casefold()
    assert result.response.endswith("?")
    assert provider.messages == []


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
        "profile_dataset",
        "get_saved_query",
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


def test_orchestrator_plan_keeps_dashboard_tools_for_publish_request() -> None:
    tools = [
        {"function": {"name": name}}
        for name in ("list_dashboards", "add_chart_to_dashboard", "create_chart")
    ]

    selected = AIOrchestrator._tools_for_plan(
        tools,
        AnalyticsTaskPlanner()
        .plan("Adicione um gráfico de vendas ao dashboard CBMES")
        .tool_names,
    )

    assert {tool["function"]["name"] for tool in selected} >= {
        "list_dashboards",
        "add_chart_to_dashboard",
        "create_chart",
    }


def test_registry_rejects_duplicate_tool_names() -> None:
    registry = ToolRegistry()
    registry.register(StubTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(StubTool())


@pytest.mark.parametrize(
    "tool_name",
    [
        "list_databases",
        "list_database_tables",
        "get_table_schema",
        "list_datasets",
        "get_dataset_schema",
        "profile_dataset",
        "list_charts",
        "list_dashboards",
        "list_saved_queries",
        "get_saved_query",
        "get_current_context",
        "run_sql_query",
        "save_sql_query",
        "create_chart",
        "edit_chart",
        "create_dashboard",
        "edit_dashboard",
        "add_chart_to_dashboard",
        "create_dataset",
    ],
)
def test_every_builtin_tool_has_an_openai_schema(tool_name: str) -> None:
    tool = create_default_registry().get(tool_name)
    assert tool is not None
    schema = tool.to_openai_tool()
    assert schema["function"]["name"] == tool_name
    assert schema["function"]["parameters"]["type"] == "object"


@pytest.mark.parametrize(
    "tool_name",
    [
        "list_databases",
        "list_database_tables",
        "get_table_schema",
        "list_datasets",
        "get_dataset_schema",
        "profile_dataset",
        "list_charts",
        "list_dashboards",
        "list_saved_queries",
        "get_saved_query",
        "get_current_context",
        "run_sql_query",
        "save_sql_query",
        "create_chart",
        "edit_chart",
        "create_dashboard",
        "edit_dashboard",
        "add_chart_to_dashboard",
        "create_dataset",
    ],
)
def test_every_builtin_tool_executes_its_registered_handler(
    tool_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from superset.extensions import security_manager

    tool = create_default_registry().get(tool_name)
    assert isinstance(tool, BuiltinTool)
    monkeypatch.setattr(security_manager, "can_access", lambda *_: True)
    monkeypatch.setattr(tool, "handler", lambda params: {"tool": tool_name, **params})
    monkeypatch.setattr(tool, "validate_params", lambda _: None)

    assert tool.execute(SimpleNamespace(), {"value": "ok"}) == ToolResult(
        True, {"tool": tool_name, "value": "ok"}
    )


@pytest.mark.parametrize(
    "tool_name",
    [
        "run_sql_query",
        "save_sql_query",
        "create_chart",
        "edit_chart",
        "create_dashboard",
        "edit_dashboard",
        "add_chart_to_dashboard",
        "create_dataset",
    ],
)
def test_each_write_tool_requires_confirmation_and_its_permission(
    tool_name: str,
) -> None:
    tool = create_default_registry().get(tool_name)
    assert tool is not None
    assert tool.requires_confirmation is True
    assert tool.required_permission is not None


def test_write_tool_rechecks_permission_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from superset.extensions import security_manager

    tool = BuiltinTool(
        "write",
        "write data",
        {"type": "object", "properties": {}},
        lambda _: {"changed": True},
        requires_confirmation=True,
        required_permission="can_ai_create_charts",
    )
    monkeypatch.setattr(security_manager, "can_access", lambda *_: False)

    result = tool.execute(SimpleNamespace(), {})

    assert result == ToolResult(False, None, "Tool access denied")


@pytest.mark.parametrize(
    ("tool_name", "params", "message"),
    [
        ("create_dataset", {"table_name": "sales"}, "database or saved_query_id"),
        (
            "create_chart",
            {
                "datasource_id": 1,
                "datasource_type": "table",
                "slice_name": "Sales",
                "viz_type": "bar",
                "params": "not-json",
            },
            "valid JSON",
        ),
    ],
)
def test_write_tools_reject_invalid_payloads_before_execution(
    tool_name: str, params: dict[str, Any], message: str
) -> None:
    tool = create_default_registry().get(tool_name)
    assert isinstance(tool, BuiltinTool)

    assert tool.validate_params(params) is not None
    assert message in tool.validate_params(params)


def test_orchestrator_executes_read_tool_and_continues_to_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    tool = StubTool()
    registry.register(tool)
    _patch_discovery(
        monkeypatch, (_discovery_candidate("international_sales", 45, 11),)
    )
    provider = StubProvider(
        [
            ProviderResponse(
                "",
                [ToolCall("call_1", "lookup", {"value": "sales"})],
            ),
            ProviderResponse("Sales dataset found."),
        ]
    )
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )
    user = SimpleNamespace(id=42)

    result = AIOrchestrator(agent, registry, user).chat(
        "Find sales", [], {"page": "sql"}
    )

    assert result.response == "Sales dataset found."
    assert result.pending_actions == []
    assert tool.calls == [{"value": "sales"}]
    assert provider.messages[1][-1]["role"] == "tool"


def test_orchestrator_only_offers_tools_enabled_for_the_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    registry.register(StubTool())
    _patch_discovery(
        monkeypatch, (_discovery_candidate("international_sales", 45, 11),)
    )
    provider = StubProvider([ProviderResponse("No tool required.")])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    agent = SimpleNamespace(
        id="agent-1",
        provider="openai",
        model="test",
        api_key_encrypted=None,
        enabled_tools=[],
    )

    AIOrchestrator(agent, registry, SimpleNamespace(id=42)).chat(
        "Find sales", [], {"page": "sql"}
    )

    assert provider.tools == [[]]


def test_saved_query_lookup_is_available_with_saved_query_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    list_tool = StubTool()
    list_tool.name = "list_saved_queries"
    lookup_tool = StubTool()
    lookup_tool.name = "get_saved_query"
    registry.register(list_tool)
    registry.register(lookup_tool)
    provider = StubProvider([ProviderResponse("No tool required.")])
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    agent = SimpleNamespace(
        id="agent-1",
        provider="openai",
        model="test",
        api_key_encrypted=None,
        enabled_tools=["list_saved_queries"],
    )

    AIOrchestrator(agent, registry, SimpleNamespace(id=42)).chat(
        "Use minha consulta salva", [], {"page": "sql"}
    )

    assert {tool["function"]["name"] for tool in provider.tools[0]} == {
        "list_saved_queries",
        "get_saved_query",
    }


def test_orchestrator_defers_write_tool_until_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    tool = StubTool(requires_confirmation=True)
    registry.register(tool)
    provider = StubProvider(
        [
            ProviderResponse(
                "I can do that.", [ToolCall("call_1", "lookup", {"value": "x"})]
            )
        ]
    )
    cache = StubCache()
    from superset.extensions import event_logger

    monkeypatch.setattr(event_logger, "log", lambda **_: None)
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    agent = SimpleNamespace(
        id="agent-1", provider="openai", model="test", api_key_encrypted=None
    )
    user = SimpleNamespace(id=42)
    orchestrator = AIOrchestrator(agent, registry, user, cache=cache)

    result = orchestrator.chat("Change it", [], {"page": "dashboard"})

    assert tool.calls == []
    action = result.pending_actions[0]
    assert action.type == "lookup"
    assert action.agent_id == "agent-1"
    assert cache.timeouts[orchestrator._cache_key(action.id)] == 600
    assert orchestrator.confirm_and_execute(action.id).data == {"value": "x"}
    assert tool.calls == [{"value": "x"}]


def test_orchestrator_accumulates_multiple_pending_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    registry.register(StubTool(requires_confirmation=True))
    provider = StubProvider(
        [
            ProviderResponse(
                "Two changes need approval.",
                [
                    ToolCall("call_1", "lookup", {"value": "a"}),
                    ToolCall("call_2", "lookup", {"value": "b"}),
                ],
            )
        ]
    )
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    orchestrator = AIOrchestrator(
        SimpleNamespace(id="agent-1", model="test", api_key_encrypted=None),
        registry,
        SimpleNamespace(id=42),
        cache=StubCache(),
    )

    result = orchestrator.chat("Change both", [], {"page": "dashboard"})

    assert [action.params for action in result.pending_actions] == [
        {"value": "a"},
        {"value": "b"},
    ]


def test_orchestrator_rejects_expired_or_wrong_agent_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    registry.register(StubTool(requires_confirmation=True))
    provider = StubProvider(
        [ProviderResponse("", [ToolCall("call_1", "lookup", {"value": "x"})])]
    )
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    cache = StubCache()
    source = AIOrchestrator(
        SimpleNamespace(id="agent-1", model="test", api_key_encrypted=None),
        registry,
        SimpleNamespace(id=42),
        cache=cache,
    )
    action = source.chat("Change", [], {"page": "dashboard"}).pending_actions[0]
    target = AIOrchestrator(
        SimpleNamespace(id="agent-2", model="test", api_key_encrypted=None),
        registry,
        SimpleNamespace(id=42),
        cache=cache,
    )

    from superset.ai.exceptions import AIActionExpiredError

    with pytest.raises(AIActionExpiredError, match="another agent"):
        target.confirm_and_execute(action.id)
    cache.delete(source._cache_key(action.id))
    with pytest.raises(AIActionExpiredError, match="not found"):
        source.confirm_and_execute(action.id)


def test_system_prompt_sanitizes_complete_context() -> None:
    prompt = AIOrchestrator._system_prompt(
        {
            "page": "<b>dashboard</b>\x00",
            "resource_id": 12,
            "resource_name": "<script>Sales</script>",
            "metadata": {"note": "\x01north"},
        }
    )

    assert "<script>" not in prompt
    assert "dashboard" in prompt
    assert "id=12" in prompt
    assert "north" in prompt


def test_ollama_system_prompt_requires_brazilian_portuguese() -> None:
    prompt = AIOrchestrator._system_prompt({"page": "home"}, "ollama")

    assert "Reply only in Brazilian Portuguese (pt-BR)" in prompt


def test_system_prompt_uses_the_agent_response_language() -> None:
    prompt = AIOrchestrator._system_prompt({"page": "home"}, "ollama", "en-US")

    assert "Reply only in English (en-US)" in prompt


def test_orchestrator_limits_tools_to_the_domains_named_in_a_request() -> None:
    tools = [
        {"function": {"name": name}}
        for name in (
            "list_databases",
            "list_datasets",
            "create_dataset",
            "list_charts",
            "create_chart",
            "list_dashboards",
            "add_chart_to_dashboard",
            "run_sql_query",
        )
    ]

    selected = AIOrchestrator._tools_for_message(
        tools,
        "Crie um dataset, gere um gráfico e adicione-o ao dashboard CBMES.",
    )

    assert {tool["function"]["name"] for tool in selected} == {
        "list_databases",
        "list_datasets",
        "create_dataset",
        "list_charts",
        "create_chart",
        "list_dashboards",
        "add_chart_to_dashboard",
    }


def test_orchestrator_keeps_all_tools_when_no_domain_is_named() -> None:
    tools = [
        {"function": {"name": "list_charts"}},
        {"function": {"name": "run_sql_query"}},
    ]

    assert AIOrchestrator._tools_for_message(tools, "Ajude-me") == tools


def test_orchestrator_bounds_and_sanitizes_history() -> None:
    history = [
        {"role": "user", "content": "x" * 2_000},
        {"role": "tool", "content": "must be ignored"},
        *[{"role": "assistant", "content": str(index)} for index in range(7)],
    ]

    compact = AIOrchestrator._compact_history(history)

    assert len(compact) == 6
    assert compact[0] == {"role": "assistant", "content": "1"}


def test_orchestrator_stops_an_endless_tool_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry()
    registry.register(StubTool())
    provider = StubProvider(
        [
            ProviderResponse("", [ToolCall(str(index), "lookup", {"value": "x"})])
            for index in range(8)
        ]
    )
    monkeypatch.setattr(
        AIOrchestrator, "_build_provider", staticmethod(lambda _: provider)
    )
    orchestrator = AIOrchestrator(
        SimpleNamespace(id="agent-1", model="test", api_key_encrypted=None),
        registry,
        SimpleNamespace(id=42),
        cache=StubCache(),
    )

    from superset.ai.exceptions import AIProviderError

    with pytest.raises(AIProviderError, match="maximum number"):
        orchestrator.chat("Loop", [], {"page": "other"})
