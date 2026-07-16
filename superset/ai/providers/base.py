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
AI Integration Plugin — Provider Adapter Interface (ABC)

Each AI provider (OpenAI, Ollama, Anthropic, etc.) must implement this
interface so the Orchestrator can call any provider through a unified
contract.

Usage pattern
-------------
1. Instantiate a concrete adapter (e.g. ``OpenAIProviderAdapter``).
2. Call ``chat_with_tools(messages, tools, model)`` inside the orchestrator
   loop to get the model's next response.
3. Inspect ``ProviderResponse.tool_calls`` — if non-empty, execute the
   relevant tools and feed results back as messages with role ``"tool"``.
4. Repeat until ``ProviderResponse.tool_calls`` is empty (final text answer)
   or a tool with ``requires_confirmation=True`` is encountered.

See docs/ai-integration/backend-api-tools.md for the full specification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from superset.utils import json

# ---------------------------------------------------------------------------
# Shared data-transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool invocation requested by the model.

    Attributes:
        id:        Opaque ID assigned by the provider (used to correlate
                   tool results in subsequent messages).
        name:      Name of the tool to execute (matches ``AITool.name``).
        arguments: Parsed JSON arguments for the tool, as a Python dict.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    """Normalised response returned by any ``AIProviderAdapter``.

    Attributes:
        content:    The assistant's text reply.  May be an empty string when
                    the model only emits tool calls without a textual message.
        tool_calls: Zero or more tool invocations requested by the model.
                    When non-empty the orchestrator must execute the tools
                    and continue the loop.
        raw:        The raw response object from the underlying SDK, kept for
                    debugging and logging purposes.  Not serialised to the
                    frontend.
    """

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class AIProviderAdapter(ABC):
    """Unified interface for all AI provider integrations.

    Concrete implementations must normalise provider-specific wire formats
    (OpenAI, Anthropic, Ollama, …) to the ``ProviderResponse`` /
    ``ToolCall`` DTOs above, so the ``AIOrchestrator`` remains
    provider-agnostic.

    Constructor convention
    ----------------------
    Subclasses should accept at minimum:
    - ``api_key: str`` — provider credential (already decrypted by the
      caller; never stored as an instance attribute in plain text beyond
      what is strictly needed for the HTTP client).
    - ``model: str`` — default model identifier forwarded to
      ``chat_with_tools`` when no override is supplied.
    - ``base_url: str | None`` — optional endpoint override for
      self-hosted / compatible APIs (Ollama, DeepSeek, …).
    """

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ProviderResponse:
        """Send a conversation turn to the provider and return its response.

        The method MUST:
        - Forward ``messages`` and ``tools`` to the provider API.
        - Normalise the provider-specific response into a ``ProviderResponse``.
        - Raise ``AIProviderError`` (from ``superset.ai.exceptions``) on any
          unrecoverable provider-side failure.

        Args:
            messages: Conversation history in OpenAI-compatible format::

                          [
                            {"role": "system",    "content": "…"},
                            {"role": "user",      "content": "…"},
                            {"role": "assistant", "content": "…",
                             "tool_calls": [{"id": "…", "function": {…}}]},
                            {"role": "tool",      "tool_call_id": "…",
                             "content": "<tool result JSON>"},
                          ]

            tools:    Tool schemas in OpenAI function-calling format::

                          [
                            {
                              "type": "function",
                              "function": {
                                "name": "list_datasets",
                                "description": "…",
                                "parameters": { … }   # JSON Schema
                              }
                            }
                          ]

            model:    Model identifier string (e.g. ``"gpt-4o"``,
                      ``"llama3.2"``, ``"claude-3-5-sonnet-20241022"``).

        Returns:
            A normalised ``ProviderResponse``.
        """
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify that the provider endpoint and credentials are reachable.

        Should perform the cheapest possible API call (e.g. list models,
        ping endpoint, or send a minimal chat completion) and return
        ``True`` on success or ``False`` on failure.  Must NOT raise
        exceptions — catch them internally and return ``False``.

        Returns:
            ``True`` if the provider is reachable and the credentials are
            accepted; ``False`` otherwise.
        """
        ...

    # ------------------------------------------------------------------
    # Helpers shared by all concrete adapters
    # ------------------------------------------------------------------

    def build_assistant_message(
        self,
        content: str,
        tool_calls: list[ToolCall],
    ) -> dict[str, Any]:
        """Return an OpenAI-compatible assistant tool-call message."""
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in tool_calls
            ],
        }

    def expand_discovery_terms(
        self, topic: str, prompt_language: str, model: str
    ) -> list[str]:
        """Return bounded semantic hints for unfamiliar discovery topics.

        Providers that cannot make a short, independently timed request keep
        the deterministic lexical discovery path by returning no extra terms.
        """
        del topic, prompt_language, model
        return []

    def build_tool_message(
        self,
        tool_call_id: str,
        result_json: str,
    ) -> dict[str, Any]:
        """Return an OpenAI-compatible ``"tool"`` role message dict.

        Convenience method so concrete adapters do not have to repeat the
        same boilerplate when feeding tool results back into the conversation.

        Args:
            tool_call_id: The ``ToolCall.id`` value returned by the provider.
            result_json:  JSON-serialised tool result string.

        Returns:
            A message dict ready to append to the ``messages`` list.
        """
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result_json,
        }
