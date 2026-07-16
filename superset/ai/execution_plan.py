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
"""Immutable, idempotent execution plans for multi-resource AI writes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from superset.ai.chart_spec import ChartSpecification
from superset.ai.exceptions import AIActionExpiredError
from superset.ai.tools.base import ToolResult
from superset.ai.tools.registry import ToolRegistry

PLAN_TTL = 600


@dataclass(frozen=True)
class PlannedAction:
    """A validated write operation in its immutable execution order."""

    tool_name: str
    params: dict[str, Any]


@dataclass(frozen=True)
class AIExecutionPlan:
    """A user- and agent-bound plan awaiting one explicit confirmation."""

    id: str
    user_id: int
    agent_id: str
    actions: tuple[PlannedAction, ...]


class ExecutionPlanService:
    """Persist, validate and execute a plan exactly once through registered tools."""

    def __init__(
        self, registry: ToolRegistry, user: Any, agent_id: str, cache: Any
    ) -> None:
        self.registry = registry
        self.user = user
        self.agent_id = agent_id
        self.cache = cache

    def create(self, actions: list[PlannedAction]) -> AIExecutionPlan:
        """Validate all actions before exposing a single confirmation to the user."""
        if not actions:
            raise ValueError("An execution plan requires at least one action")
        for action in actions:
            self._validate(action)
        self._validate_references(actions)
        plan = AIExecutionPlan(
            str(uuid4()), self.user.id, self.agent_id, tuple(actions)
        )
        self.cache.set(
            self._key(plan.id),
            {"plan": asdict(plan), "status": "pending"},
            timeout=PLAN_TTL,
        )
        return plan

    def confirm_and_execute(  # noqa: C901
        self,
        plan_id: str,
        on_step: Callable[[int, PlannedAction, ToolResult], None] | None = None,
    ) -> list[ToolResult]:
        """Execute a bound plan once, stopping on the first failed action."""
        record = self.cache.get(self._key(plan_id))
        if record is None:
            raise AIActionExpiredError("AI execution plan was not found or has expired")
        plan = record["plan"]
        if plan["user_id"] != self.user.id or plan["agent_id"] != self.agent_id:
            raise AIActionExpiredError(
                "AI execution plan does not belong to this user or agent"
            )
        if record["status"] == "executed":
            return [ToolResult(**result) for result in record["results"]]
        if record["status"] != "pending":
            raise AIActionExpiredError("AI execution plan cannot be executed")
        if not self.cache.add(self._lock_key(plan_id), True, timeout=PLAN_TTL):
            latest = self.cache.get(self._key(plan_id))
            if latest and latest["status"] == "executed":
                return [ToolResult(**result) for result in latest["results"]]
            raise AIActionExpiredError("AI execution plan is already executing")
        results: list[ToolResult] = []
        try:
            for item in plan["actions"]:
                action = PlannedAction(item["tool_name"], item["params"])
                resolved_action = PlannedAction(
                    action.tool_name, self._resolve_references(action.params, results)
                )
                self._validate(resolved_action)
                tool = self.registry.get(action.tool_name)
                assert tool is not None
                if tool not in self.registry.tools_for_user(self.user):
                    raise AIActionExpiredError(
                        "AI execution plan is no longer authorized"
                    )
                result = tool.execute(self.user, resolved_action.params)
                results.append(result)
                if on_step:
                    on_step(len(results), resolved_action, result)
                if not result.success:
                    self.cache.set(
                        self._key(plan_id),
                        {
                            "plan": plan,
                            "status": "failed",
                            "results": [asdict(value) for value in results],
                        },
                        timeout=PLAN_TTL,
                    )
                    return results
            self.cache.set(
                self._key(plan_id),
                {
                    "plan": plan,
                    "status": "executed",
                    "results": [asdict(value) for value in results],
                },
                timeout=PLAN_TTL,
            )
            return results
        finally:
            self.cache.delete(self._lock_key(plan_id))

    def cancel(self, plan_id: str) -> None:
        """Discard an unexecuted plan owned by the current user and agent."""
        record = self.cache.get(self._key(plan_id))
        if record is None or record["plan"]["agent_id"] != self.agent_id:
            raise AIActionExpiredError("AI execution plan was not found or has expired")
        if record["status"] != "pending":
            raise AIActionExpiredError("AI execution plan cannot be cancelled")
        self.cache.delete(self._key(plan_id))

    def _validate(self, action: PlannedAction) -> None:
        tool = self.registry.get(action.tool_name)
        if tool is None or not tool.requires_confirmation:
            raise ValueError(f"Invalid planned write action: {action.tool_name}")
        if self._contains_reference(action.params):
            return
        if action.tool_name == "create_chart" and "chart_spec" in action.params:
            ChartSpecification.from_dict(action.params["chart_spec"])
        validator = getattr(tool, "validate_params", lambda _: None)
        if error := validator(action.params):
            raise ValueError(error)

    @classmethod
    def _validate_references(cls, actions: list[PlannedAction]) -> None:
        """Allow only backward references to an earlier action result id."""
        for index, action in enumerate(actions):
            for reference in cls._references(action.params):
                parts = reference.split(".")
                if (
                    len(parts) != 3
                    or parts[0] != "actions"
                    or parts[2] != "id"
                    or not parts[1].isdigit()
                    or int(parts[1]) >= index
                ):
                    raise ValueError(f"Invalid planned action reference: {reference}")

    @classmethod
    def _resolve_references(cls, value: Any, results: list[ToolResult]) -> Any:
        if isinstance(value, dict) and set(value) == {"$ref"}:
            parts = value["$ref"].split(".")
            if len(parts) != 3 or not parts[1].isdigit():
                raise ValueError("Invalid planned action reference")
            result = results[int(parts[1])]
            if not result.success or not isinstance(result.data, dict):
                raise ValueError("Referenced planned action did not return an id")
            return result.data[parts[2]]
        if isinstance(value, dict):
            return {
                key: cls._resolve_references(item, results)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._resolve_references(item, results) for item in value]
        return value

    @classmethod
    def _references(cls, value: Any) -> list[str]:
        if isinstance(value, dict) and set(value) == {"$ref"}:
            return [str(value["$ref"])]
        if isinstance(value, dict):
            return [
                reference
                for item in value.values()
                for reference in cls._references(item)
            ]
        if isinstance(value, list):
            return [reference for item in value for reference in cls._references(item)]
        return []

    @classmethod
    def _contains_reference(cls, value: Any) -> bool:
        return bool(cls._references(value))

    def _key(self, plan_id: str) -> str:
        return f"ai_execution_plan:{self.user.id}:{plan_id}"

    def _lock_key(self, plan_id: str) -> str:
        return f"{self._key(plan_id)}:lock"
