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
"""Base types for safe, provider-agnostic AI tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """The serialisable result of an AI tool execution."""

    success: bool
    data: Any
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the provider-safe representation used in tool messages."""
        return {"success": self.success, "data": self.data, "error": self.error}


class AITool(ABC):
    """A Superset operation exposed to an AI provider as a function."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    requires_confirmation = False
    required_permission: str | None = None

    @abstractmethod
    def execute(self, user: Any, params: dict[str, Any]) -> ToolResult:
        """Execute the operation in the current user's security context."""

    def to_openai_tool(self) -> dict[str, Any]:
        """Serialise the tool using the common OpenAI function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
