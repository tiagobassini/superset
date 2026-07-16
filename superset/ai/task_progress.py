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
"""Redis-backed, user-bound progress events for AI analytics tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from superset.ai.orchestrator import OrchestratorResult

TASK_TTL = 600
TaskState = Literal[
    "planning",
    "discovering",
    "analyzing",
    "awaiting_confirmation",
    "executing",
    "awaiting_user_input",
    "completed",
    "failed",
]

TERMINAL_STATES = {
    "awaiting_confirmation",
    "awaiting_user_input",
    "completed",
    "failed",
}


@dataclass(frozen=True)
class TaskEvent:
    """A safe status update emitted to the chat client."""

    sequence: int
    state: str
    message: str
    step: str | None = None
    data: dict[str, Any] | None = None
    timestamp: str | None = None


class AITaskProgress:
    """Persist task events so clients can poll or reconnect to an SSE stream."""

    def __init__(self, cache: Any, user_id: int, agent_id: str) -> None:
        self.cache = cache
        self.user_id = user_id
        self.agent_id = agent_id

    def create(self) -> str:
        """Create an empty user- and agent-bound task."""
        task_id = str(uuid4())
        self.cache.set(
            self._key(task_id),
            {
                "user_id": self.user_id,
                "agent_id": self.agent_id,
                "status": "planning",
                "events": [],
            },
            timeout=TASK_TTL,
        )
        return task_id

    def emit(
        self,
        task_id: str,
        state: TaskState,
        message: str,
        step: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> TaskEvent:
        """Append a public progress event and refresh the bounded task TTL."""
        record = self._record(task_id)
        event = TaskEvent(
            len(record["events"]) + 1,
            state,
            message,
            step,
            data,
            datetime.now(timezone.utc).isoformat(),
        )
        record["events"].append(
            {
                "task_id": task_id,
                "sequence": event.sequence,
                "state": event.state,
                "message": event.message,
                "step": event.step,
                "data": event.data,
                "timestamp": event.timestamp,
            }
        )
        record["status"] = state
        self.cache.set(self._key(task_id), record, timeout=TASK_TTL)
        return event

    def events(self, task_id: str, after: int = 0) -> list[dict[str, Any]]:
        """Return events after a sequence number for polling or SSE reconnects."""
        return [
            event
            for event in self._record(task_id)["events"]
            if event["sequence"] > after
        ]

    def snapshot(self, task_id: str, after: int = 0) -> dict[str, Any]:
        """Return the public task state used by polling clients after a reload."""
        record = self._record(task_id)
        return {
            "task_id": task_id,
            "status": record["status"],
            "events": [
                event for event in record["events"] if event["sequence"] > after
            ],
            "response": record.get("response"),
            "pending_actions": record.get("pending_actions", []),
            "execution_plan": record.get("execution_plan"),
        }

    def complete(self, task_id: str, result: OrchestratorResult) -> None:
        """Emit the terminal state appropriate for chat confirmation semantics."""
        record = self._record(task_id)
        record["response"] = result.response
        record["pending_actions"] = [
            action.to_dict() for action in result.pending_actions
        ]
        record["execution_plan"] = result.execution_plan
        if result.execution_plan:
            record["pending_actions"] = [
                {
                    "id": result.execution_plan["id"],
                    "type": "execution_plan",
                    "description": "Confirmar o plano completo",
                    "params": {**result.execution_plan, "task_id": task_id},
                    "requires_confirmation": True,
                    "status": "pending",
                }
            ]
        self.cache.set(self._key(task_id), record, timeout=TASK_TTL)
        if result.pending_actions or result.execution_plan:
            self.emit(
                task_id,
                "awaiting_confirmation",
                "Aguardando sua confirmação.",
                "confirmation",
            )
        elif result.response.rstrip().endswith("?"):
            self.emit(
                task_id,
                "awaiting_user_input",
                "Preciso de uma informação adicional para continuar.",
                "clarification",
            )
        else:
            self.emit(task_id, "completed", "Análise concluída.", "summary")

    def complete_plan(self, task_id: str, results: list[Any]) -> None:
        """Publish the immutable plan outcome after all executable steps finish."""
        record = self._record(task_id)
        record["pending_actions"] = []
        successful = all(result.success for result in results)
        summary = [
            result.data
            for result in results
            if result.success and isinstance(result.data, dict)
        ]
        record["response"] = (
            "Plano concluído com sucesso. Recursos criados ou reutilizados: "
            f"{summary}"
            if successful
            else "O plano foi interrompido após uma etapa falhar. "
            f"Resultados: {[result.to_dict() for result in results]}"
        )
        self.cache.set(self._key(task_id), record, timeout=TASK_TTL)
        self.emit(
            task_id,
            "completed" if successful else "failed",
            "Plano concluído." if successful else "Falha durante a execução do plano.",
            "summary",
        )

    def _record(self, task_id: str) -> dict[str, Any]:
        record = self.cache.get(self._key(task_id))
        if (
            record is None
            or record["user_id"] != self.user_id
            or record["agent_id"] != self.agent_id
        ):
            raise KeyError("AI task was not found or access was denied")
        return record

    def _key(self, task_id: str) -> str:
        return f"ai_task:{self.user_id}:{task_id}"
