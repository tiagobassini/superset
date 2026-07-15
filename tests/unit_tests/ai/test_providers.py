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
"""Unit tests for AI provider adapters using mocked external clients."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from superset.ai.exceptions import AIProviderError
from superset.ai.providers.anthropic_provider import AnthropicProviderAdapter
from superset.ai.providers.base import ToolCall
from superset.ai.providers.ollama_provider import OllamaProviderAdapter
from superset.ai.providers.openai_provider import OpenAIProviderAdapter


def test_openai_adapter_normalizes_tool_calls() -> None:
    client = MagicMock()
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(
                    name="list_datasets", arguments='{"search": "sales"}'
                ),
            )
        ],
    )
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message)]
    )
    adapter = OpenAIProviderAdapter(api_key="unused", client=client)

    result = adapter.chat_with_tools(
        messages=[{"role": "user", "content": "List datasets"}],
        tools=[{"type": "function", "function": {"name": "list_datasets"}}],
        model="deepseek-chat",
    )

    assert result.content == ""
    assert result.tool_calls[0].name == "list_datasets"
    assert result.tool_calls[0].arguments == {"search": "sales"}
    client.chat.completions.create.assert_called_once_with(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "List datasets"}],
        tools=[{"type": "function", "function": {"name": "list_datasets"}}],
    )


def test_openai_adapter_rejects_invalid_tool_arguments() -> None:
    client = MagicMock()
    message = SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name="list_datasets", arguments="not-json"),
            )
        ],
    )
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message)]
    )

    with pytest.raises(AIProviderError, match="invalid tool-call arguments"):
        OpenAIProviderAdapter(api_key="unused", client=client).chat_with_tools(
            messages=[], tools=[], model="gpt-4o"
        )


def test_openai_adapter_tests_connection_without_raising() -> None:
    client = MagicMock()
    adapter = OpenAIProviderAdapter(api_key="unused", client=client)
    assert adapter.test_connection() is True
    client.models.list.assert_called_once()

    client.models.list.side_effect = RuntimeError("unauthorized")
    assert adapter.test_connection() is False


def test_ollama_adapter_normalizes_native_tool_calls() -> None:
    client = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_dataset_schema",
                        "arguments": {"dataset_id": 12},
                    }
                }
            ],
        }
    }
    client.post.return_value = response
    adapter = OllamaProviderAdapter(client=client)

    result = adapter.chat_with_tools(messages=[], tools=[], model="llama3.2")

    assert result.tool_calls[0].name == "get_dataset_schema"
    assert result.tool_calls[0].arguments == {"dataset_id": 12}
    assert result.tool_calls[0].id
    client.post.assert_called_once_with(
        "/api/chat",
        json={
            "model": "llama3.2",
            "messages": [],
            "tools": [],
            "stream": False,
            "think": False,
        },
    )


def test_ollama_adapter_normalizes_qwen_content_tool_call() -> None:
    client = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "message": {
            "content": '{"name":"list_database_tables","arguments":{"database_id":1}}'
        }
    }
    client.post.return_value = response

    result = OllamaProviderAdapter(client=client).chat_with_tools(
        messages=[], tools=[], model="qwen3:1.7b"
    )

    assert result.content == ""
    assert [(call.name, call.arguments) for call in result.tool_calls] == [
        ("list_database_tables", {"database_id": 1})
    ]


def test_ollama_adapter_tests_connection_without_raising() -> None:
    client = MagicMock()
    adapter = OllamaProviderAdapter(client=client)
    assert adapter.test_connection() is True
    client.get.assert_called_once_with("/api/tags")

    client.get.return_value.raise_for_status.side_effect = RuntimeError("offline")
    assert adapter.test_connection() is False


def test_ollama_adapter_uses_native_messages_for_tool_results() -> None:
    adapter = OllamaProviderAdapter(client=MagicMock())
    tool_call = ToolCall("call_1", "list_dashboards", {"page": 0})

    assert adapter.build_assistant_message("", [tool_call]) == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "function": {
                    "name": "list_dashboards",
                    "arguments": {"page": 0},
                },
            }
        ],
    }
    assert adapter.build_tool_message("call_1", '{"success": true}') == {
        "role": "tool",
        "content": '{"success": true}',
    }


def test_anthropic_adapter_converts_tools_messages_and_response() -> None:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Vou consultar os datasets."),
            SimpleNamespace(
                type="tool_use",
                id="toolu_1",
                name="list_datasets",
                input={"search": "sales"},
            ),
        ]
    )
    adapter = AnthropicProviderAdapter(api_key="unused", client=client)

    result = adapter.chat_with_tools(
        messages=[
            {"role": "system", "content": "Você é um assistente de BI."},
            {"role": "user", "content": "Liste os datasets de vendas."},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "list_datasets",
                    "description": "Lista datasets",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        model="claude-3-5-sonnet-latest",
    )

    assert result.content == "Vou consultar os datasets."
    assert result.tool_calls[0].id == "toolu_1"
    assert result.tool_calls[0].arguments == {"search": "sales"}
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "Você é um assistente de BI."
    assert kwargs["messages"] == [
        {"role": "user", "content": "Liste os datasets de vendas."}
    ]
    assert kwargs["tools"][0]["input_schema"] == {"type": "object", "properties": {}}


def test_anthropic_adapter_converts_tool_results_to_user_content_blocks() -> None:
    system, messages = AnthropicProviderAdapter._convert_messages(
        [
            {"role": "system", "content": "system"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "list_datasets",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "[]"},
        ]
    )

    assert system == "system"
    assert messages[0]["content"][0]["type"] == "tool_use"
    assert messages[1] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "[]"}
        ],
    }


def test_anthropic_adapter_tests_connection_without_raising() -> None:
    client = MagicMock()
    adapter = AnthropicProviderAdapter(
        api_key="unused", model="claude-test", client=client
    )
    assert adapter.test_connection() is True
    client.messages.create.assert_called_once_with(
        model="claude-test",
        max_tokens=1,
        messages=[{"role": "user", "content": "ping"}],
    )

    client.messages.create.side_effect = RuntimeError("unauthorized")
    assert adapter.test_connection() is False
