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

import json
from typing import Any
from uuid import uuid4

from superset.ai.exceptions import AIProviderError
from superset.ai.providers.base import AIProviderAdapter, ProviderResponse, ToolCall


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
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0)

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
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload["message"]
            tool_calls = [
                self._to_tool_call(call) for call in message.get("tool_calls", [])
            ]
            return ProviderResponse(
                content=message.get("content") or "", tool_calls=tool_calls, raw=payload
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
