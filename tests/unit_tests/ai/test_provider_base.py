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
"""
Unit tests for AIProviderAdapter ABC and the shared DTOs.

These tests verify:
- ToolCall and ProviderResponse dataclasses are correctly constructed.
- AIProviderAdapter cannot be instantiated directly (enforces ABC).
- A concrete subclass that implements the abstract methods can be instantiated.
- build_tool_message produces the expected OpenAI-compatible dict.
- Concrete adapter correctly returns ProviderResponse with tool_calls.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from superset.ai.providers.base import AIProviderAdapter, ProviderResponse, ToolCall


# ---------------------------------------------------------------------------
# Minimal concrete adapter used across tests
# ---------------------------------------------------------------------------


class _StubAdapter(AIProviderAdapter):
    """Minimal concrete implementation used only in tests."""

    def __init__(self) -> None:
        self._connection_ok = True
        self._response: ProviderResponse = ProviderResponse(content="ok")

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ProviderResponse:
        return self._response

    def test_connection(self) -> bool:
        return self._connection_ok


# ---------------------------------------------------------------------------
# ToolCall dataclass
# ---------------------------------------------------------------------------


def test_tool_call_construction() -> None:
    tc = ToolCall(id="call_abc", name="list_datasets", arguments={"search": "sales"})
    assert tc.id == "call_abc"
    assert tc.name == "list_datasets"
    assert tc.arguments == {"search": "sales"}


def test_tool_call_default_arguments() -> None:
    tc = ToolCall(id="x", name="y", arguments={})
    assert tc.arguments == {}


# ---------------------------------------------------------------------------
# ProviderResponse dataclass
# ---------------------------------------------------------------------------


def test_provider_response_defaults() -> None:
    resp = ProviderResponse(content="Hello")
    assert resp.content == "Hello"
    assert resp.tool_calls == []
    assert resp.raw is None


def test_provider_response_with_tool_calls() -> None:
    tc = ToolCall(id="call_1", name="create_chart", arguments={"viz_type": "bar"})
    resp = ProviderResponse(content="", tool_calls=[tc], raw={"id": "chatcmpl-xyz"})
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "create_chart"
    assert resp.raw == {"id": "chatcmpl-xyz"}


def test_provider_response_tool_calls_are_independent() -> None:
    """Two ProviderResponse instances must not share the same tool_calls list."""
    r1 = ProviderResponse(content="a")
    r2 = ProviderResponse(content="b")
    r1.tool_calls.append(ToolCall(id="x", name="y", arguments={}))
    assert r2.tool_calls == [], "Mutable default must not be shared between instances"


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------


def test_abc_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        AIProviderAdapter()  # type: ignore[abstract]


def test_abstract_methods_are_declared() -> None:
    abstract = getattr(AIProviderAdapter, "__abstractmethods__", set())
    assert "chat_with_tools" in abstract
    assert "test_connection" in abstract


def test_concrete_subclass_can_be_instantiated() -> None:
    adapter = _StubAdapter()
    assert isinstance(adapter, AIProviderAdapter)


def test_concrete_subclass_missing_one_method_raises() -> None:
    class _Incomplete(AIProviderAdapter):
        def chat_with_tools(self, messages, tools, model):  # type: ignore[override]
            return ProviderResponse(content="")

        # test_connection intentionally missing

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# build_tool_message helper
# ---------------------------------------------------------------------------


def test_build_tool_message_structure() -> None:
    adapter = _StubAdapter()
    result = {"data": [1, 2, 3]}
    msg = adapter.build_tool_message("call_42", json.dumps(result))

    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call_42"
    assert json.loads(msg["content"]) == result


def test_build_tool_message_preserves_json_string() -> None:
    adapter = _StubAdapter()
    raw_json = '{"success": true, "data": null}'
    msg = adapter.build_tool_message("call_1", raw_json)
    assert msg["content"] == raw_json


# ---------------------------------------------------------------------------
# chat_with_tools contract via stub
# ---------------------------------------------------------------------------


def test_chat_with_tools_returns_provider_response() -> None:
    adapter = _StubAdapter()
    expected = ProviderResponse(
        content="Here are the datasets:",
        tool_calls=[ToolCall(id="c1", name="list_datasets", arguments={})],
    )
    adapter._response = expected

    result = adapter.chat_with_tools(
        messages=[{"role": "user", "content": "List all datasets"}],
        tools=[{"type": "function", "function": {"name": "list_datasets"}}],
        model="gpt-4o",
    )

    assert isinstance(result, ProviderResponse)
    assert result.content == "Here are the datasets:"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "list_datasets"


def test_chat_with_tools_empty_tool_calls_on_final_answer() -> None:
    adapter = _StubAdapter()
    adapter._response = ProviderResponse(content="Final answer, no tools needed.")

    result = adapter.chat_with_tools(
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
        model="llama3.2",
    )

    assert result.tool_calls == []
    assert result.content == "Final answer, no tools needed."


# ---------------------------------------------------------------------------
# test_connection contract via stub
# ---------------------------------------------------------------------------


def test_test_connection_returns_true_when_reachable() -> None:
    adapter = _StubAdapter()
    adapter._connection_ok = True
    assert adapter.test_connection() is True


def test_test_connection_returns_false_when_unreachable() -> None:
    adapter = _StubAdapter()
    adapter._connection_ok = False
    assert adapter.test_connection() is False
