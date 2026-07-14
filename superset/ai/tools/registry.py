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
"""Central registry for the operations exposed to AI providers."""

from __future__ import annotations

from typing import Any

from superset.ai.tools.base import AITool


class ToolRegistry:
    """Register and retrieve unique tools without coupling to a provider."""

    def __init__(self) -> None:
        self._tools: dict[str, AITool] = {}

    def register(self, tool: AITool) -> None:
        """Register a tool, rejecting duplicate or incomplete definitions."""
        if not tool.name:
            raise ValueError("AI tools must define a name")
        if tool.name in self._tools:
            raise ValueError(f"AI tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AITool | None:
        """Return a tool by name, if it has been registered."""
        return self._tools.get(name)

    def tools_for_user(self, user: Any) -> list[AITool]:
        """Return tools the current user is permitted to invoke."""
        return [tool for tool in self._tools.values() if self._can_use(tool, user)]

    def openai_tools_for_user(self, user: Any) -> list[dict[str, Any]]:
        """Return function schemas for all tools available to a user."""
        return [tool.to_openai_tool() for tool in self.tools_for_user(user)]

    @staticmethod
    def _can_use(tool: AITool, user: Any) -> bool:
        """Check an optional explicit AI permission in the active request context."""
        if tool.required_permission is None:
            return True
        from superset.extensions import security_manager

        return security_manager.can_access(tool.required_permission, "AIAgentResource")


def create_default_registry() -> ToolRegistry:
    """Build the standard registry once per orchestration request."""
    from superset.ai.tools.builtin import default_tools

    registry = ToolRegistry()
    for tool in default_tools():
        registry.register(tool)
    return registry
