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
"""Adapter for Ollama's native REST API."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from superset.ai.exceptions import AIProviderError
from superset.ai.providers.base import AIProviderAdapter, ProviderResponse, ToolCall
from superset.utils import json

OLLAMA_REQUEST_TIMEOUT_SECONDS = 120.0


class OllamaProviderAdapter(AIProviderAdapter):
    """Adapt Ollama's ``/api/chat`` tool calling format to the common contract."""

    def __init__(
        self, base_url: str = "http://localhost:11434", client: Any | None = None
    ) -> None:
        """Create an adapter, optionally using a supplied HTTP client for tests."""
        if client is not None:
            self.client = client
            return
        try:
            import httpx
        except ImportError as ex:
            raise AIProviderError(
                "Ollama support requires the 'ai' optional dependency. "
                "Install apache-superset[ai]."
            ) from ex
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS
        )

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ProviderResponse:
        """Call Ollama's chat endpoint without streaming and normalise tool calls."""
        try:
            response = self.client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "stream": False,
                    # Qwen3's hidden reasoning consumes output tokens and delays
                    # tool calls without adding value to Superset operations.
                    "think": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload["message"]
            tool_calls = [
                self._to_tool_call(call) for call in message.get("tool_calls", [])
            ]
            content = message.get("content") or ""
            if not tool_calls:
                tool_calls = self._tool_calls_from_content(content)
            return ProviderResponse(
                content="" if tool_calls else content,
                tool_calls=tool_calls,
                raw=payload,
            )
        except AIProviderError:
            raise
        except Exception as ex:
            raise AIProviderError("Ollama chat request failed") from ex

    def test_connection(self) -> bool:
        """Verify that the Ollama server responds to its tags endpoint."""
        try:
            response = self.client.get("/api/tags")
            response.raise_for_status()
        except Exception:
            return False
        return True

    def build_assistant_message(
        self,
        content: str,
        tool_calls: list[ToolCall],
    ) -> dict[str, Any]:
        """Return a native Ollama tool-call message for the next turn."""
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": call.id,
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in tool_calls
            ],
        }

    def build_tool_message(
        self,
        tool_call_id: str,
        result_json: str,
    ) -> dict[str, Any]:
        """Return Ollama's native tool-result message without OpenAI fields."""
        return {"role": "tool", "content": result_json}

    @staticmethod
    def _to_tool_call(tool_call: dict[str, Any]) -> ToolCall:
        """Convert an Ollama tool-call object to the common representation."""
        function = tool_call.get("function", {})
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as ex:
                raise AIProviderError(
                    "Ollama returned invalid tool-call arguments"
                ) from ex
        if not isinstance(arguments, dict) or not isinstance(function.get("name"), str):
            raise AIProviderError("Ollama returned an invalid tool call")
        return ToolCall(
            id=tool_call.get("id") or str(uuid4()),
            name=function["name"],
            arguments=arguments,
        )

    @staticmethod
    def _tool_calls_from_content(content: str) -> list[ToolCall]:
        """Handle Qwen models that serialise a tool call in message content.

        Ollama normally returns ``message.tool_calls``. Some Qwen responses use
        a JSON object in ``message.content`` instead, so accepting only the
        native field makes a requested operation look like ordinary prose.
        """
        try:
            value = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return []
        calls = value.get("tool_calls", []) if isinstance(value, dict) else []
        if isinstance(value, dict) and {"name", "arguments"} <= value.keys():
            calls = [value]
        parsed: list[ToolCall] = []
        for call in calls:
            if not isinstance(call, dict):
                return []
            if "function" in call:
                parsed.append(OllamaProviderAdapter._to_tool_call(call))
                continue
            name = call.get("name")
            arguments = call.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return []
            parsed.append(ToolCall(id=str(uuid4()), name=name, arguments=arguments))
        return parsed
