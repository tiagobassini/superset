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
"""OpenAI-compatible provider adapter for OpenAI, DeepSeek, and Codex."""

from __future__ import annotations

import json
from typing import Any

from superset.ai.exceptions import AIProviderError
from superset.ai.providers.base import AIProviderAdapter, ProviderResponse, ToolCall


class OpenAIProviderAdapter(AIProviderAdapter):
    """Adapt OpenAI-compatible chat-completions APIs to the common contract."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        """Create an adapter, optionally using a supplied SDK client for tests."""
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI
        except ImportError as ex:
            raise AIProviderError(
                "OpenAI support requires the 'ai' optional dependency. "
                "Install apache-superset[ai]."
            ) from ex
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ProviderResponse:
        """Run a chat completion and normalise its function calls."""
        try:
            response = self.client.chat.completions.create(
                model=model, messages=messages, tools=tools or None
            )
            message = response.choices[0].message
            tool_calls = [
                ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=self._parse_arguments(tool_call.function.arguments),
                )
                for tool_call in message.tool_calls or []
            ]
            return ProviderResponse(
                content=message.content or "", tool_calls=tool_calls, raw=response
            )
        except AIProviderError:
            raise
        except Exception as ex:
            raise AIProviderError("OpenAI-compatible chat request failed") from ex

    def test_connection(self) -> bool:
        """Verify credentials and endpoint availability with a models request."""
        try:
            self.client.models.list()
        except Exception:
            return False
        return True

    @staticmethod
    def _parse_arguments(arguments: str | None) -> dict[str, Any]:
        """Parse provider-supplied function arguments as a JSON object."""
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError as ex:
            raise AIProviderError(
                "Provider returned invalid tool-call arguments"
            ) from ex
        if not isinstance(parsed, dict):
            raise AIProviderError("Provider tool-call arguments must be a JSON object")
        return parsed
