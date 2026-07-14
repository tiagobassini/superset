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
"""Adapter for Anthropic's Messages API."""

from __future__ import annotations

import json
from typing import Any

from superset.ai.exceptions import AIProviderError
from superset.ai.providers.base import AIProviderAdapter, ProviderResponse, ToolCall


class AnthropicProviderAdapter(AIProviderAdapter):
    """Translate the common OpenAI-like messages to Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-haiku-latest",
        client: Any | None = None,
    ) -> None:
        """Create an adapter, optionally using a supplied SDK client for tests."""
        self.model = model
        if client is not None:
            self.client = client
            return
        try:
            from anthropic import Anthropic
        except ImportError as ex:
            raise AIProviderError(
                "Anthropic support requires the 'ai' optional dependency. "
                "Install apache-superset[ai]."
            ) from ex
        self.client = Anthropic(api_key=api_key)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ProviderResponse:
        """Call Anthropic Messages and normalise text and ``tool_use`` blocks."""
        try:
            system, converted_messages = self._convert_messages(messages)
            response = self.client.messages.create(
                model=model,
                max_tokens=1024,
                system=system or None,
                messages=converted_messages,
                tools=[self._convert_tool(tool) for tool in tools] or None,
            )
            tool_calls = [
                ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                for block in response.content
                if block.type == "tool_use"
            ]
            content = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return ProviderResponse(
                content=content, tool_calls=tool_calls, raw=response
            )
        except AIProviderError:
            raise
        except Exception as ex:
            raise AIProviderError("Anthropic chat request failed") from ex

    def test_connection(self) -> bool:
        """Send the smallest Messages API request that validates the API key."""
        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
        except Exception:
            return False
        return True

    @staticmethod
    def _convert_tool(tool: dict[str, Any]) -> dict[str, Any]:
        """Convert an OpenAI function schema to Anthropic's tool schema."""
        function = tool.get("function", tool)
        name = function.get("name")
        if not isinstance(name, str):
            raise AIProviderError("Tool definition must include a function name")
        return {
            "name": name,
            "description": function.get("description", ""),
            "input_schema": function.get(
                "parameters", {"type": "object", "properties": {}}
            ),
        }

    @classmethod
    def _convert_messages(
        cls, messages: list[dict[str, Any]]
    ) -> tuple[str, list[dict[str, Any]]]:
        """Convert OpenAI-like history to Anthropic's system/messages split."""
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content") or ""
            if role == "system":
                system_parts.append(str(content))
                continue
            if role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": message.get("tool_call_id"),
                    "content": str(content),
                }
                cls._append_message(converted, "user", [block])
                continue
            if role not in {"user", "assistant"}:
                raise AIProviderError(f"Unsupported Anthropic message role: {role}")
            if role == "assistant" and message.get("tool_calls"):
                blocks: list[dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                for tool_call in message["tool_calls"]:
                    function = tool_call.get("function", {})
                    arguments = function.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError as ex:
                            raise AIProviderError(
                                "Tool-call arguments must be valid JSON"
                            ) from ex
                    if not isinstance(arguments, dict):
                        raise AIProviderError(
                            "Tool-call arguments must be a JSON object"
                        )
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.get("id"),
                            "name": function.get("name"),
                            "input": arguments,
                        }
                    )
                cls._append_message(converted, role, blocks)
            else:
                cls._append_message(converted, role, str(content))
        return "\n\n".join(system_parts), converted

    @staticmethod
    def _append_message(
        messages: list[dict[str, Any]], role: str, content: Any
    ) -> None:
        """Merge adjacent same-role messages, which Anthropic does not accept."""
        if messages and messages[-1]["role"] == role:
            previous = messages[-1]["content"]
            if isinstance(previous, list):
                previous.extend(
                    content
                    if isinstance(content, list)
                    else [{"type": "text", "text": content}]
                )
            else:
                messages[-1]["content"] = f"{previous}\n{content}"
            return
        messages.append({"role": role, "content": content})
