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

import re
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


def _escape_markdown_link_text(value: Any) -> str:
    """Escape the minimal Markdown syntax used for artifact names."""

    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


MESSAGES = {
    "pt-BR": {
        "plan_success": "Plano concluído com sucesso.",
        "no_resources": "Nenhum recurso retornado.",
        "plan_failed": "O plano foi interrompido porque uma etapa falhou.",
        "failed_step": "Etapa {index}: {error}",
        "chart_exists": (
            'O gráfico "{name}" já existe usando outra fonte de dados. '
            "Para continuar, escolha outro nome para o gráfico ou remova o "
            "gráfico existente."
        ),
        "plan_completed_event": "Plano concluído.",
        "plan_failed_event": "Falha durante a execução do plano.",
    },
    "en-US": {
        "plan_success": "The plan finished successfully.",
        "no_resources": "No resources were returned.",
        "plan_failed": "The plan stopped because one step failed.",
        "failed_step": "Step {index}: {error}",
        "chart_exists": (
            'Chart "{name}" already exists with a different datasource. '
            "To continue, choose another chart name or remove the existing chart."
        ),
        "plan_completed_event": "Plan completed.",
        "plan_failed_event": "Plan execution failed.",
    },
    "es-ES": {
        "plan_success": "El plan finalizó correctamente.",
        "no_resources": "No se devolvió ningún recurso.",
        "plan_failed": "El plan se interrumpió porque falló una etapa.",
        "failed_step": "Etapa {index}: {error}",
        "chart_exists": (
            'El gráfico "{name}" ya existe con otra fuente de datos. '
            "Para continuar, elige otro nombre para el gráfico o elimina el "
            "gráfico existente."
        ),
        "plan_completed_event": "Plan finalizado.",
        "plan_failed_event": "Falló la ejecución del plan.",
    },
    "fr-FR": {
        "plan_success": "Le plan s'est terminé avec succès.",
        "no_resources": "Aucune ressource n'a été renvoyée.",
        "plan_failed": "Le plan s'est arrêté car une étape a échoué.",
        "failed_step": "Étape {index} : {error}",
        "chart_exists": (
            'Le graphique "{name}" existe déjà avec une autre source de données. '
            "Pour continuer, choisissez un autre nom de graphique ou supprimez "
            "le graphique existant."
        ),
        "plan_completed_event": "Plan terminé.",
        "plan_failed_event": "Échec de l'exécution du plan.",
    },
}


def _message(language: str, key: str, **kwargs: Any) -> str:
    """Return a localized task message, falling back to Brazilian Portuguese."""

    template = MESSAGES.get(language, MESSAGES["pt-BR"])[key]
    return template.format(**kwargs)


def _resource_summary(resources: list[dict[str, Any]]) -> str:
    """Return a human-readable summary for created or reused resources."""

    lines = []
    for resource in resources:
        name = (
            resource.get("chart_name")
            or resource.get("dashboard_title")
            or resource.get("table_name")
            or resource.get("label")
            or resource.get("name")
            or resource.get("id")
        )
        url = resource.get("url") or _dashboard_url(resource)
        if url and name:
            lines.append(f"- [{_escape_markdown_link_text(name)}]({url})")
        elif name:
            lines.append(f"- {name}")
        else:
            lines.append(f"- {resource}")
    return "\n".join(lines)


def _dashboard_url(resource: dict[str, Any]) -> str | None:
    """Return a dashboard URL for publication action results."""

    dashboard_id = resource.get("dashboard_id")
    if isinstance(dashboard_id, int) and not isinstance(dashboard_id, bool):
        return f"/superset/dashboard/{dashboard_id}/"
    return None


def _friendly_error(error: str | None, language: str) -> str:
    """Convert safe technical tool errors into user-facing guidance."""

    if not error:
        return _message(language, "plan_failed")

    chart_exists = re.fullmatch(
        r"Chart `(?P<name>.+)` already exists with another datasource", error
    )
    if chart_exists:
        return _message(language, "chart_exists", name=chart_exists.group("name"))

    return error


def _failure_summary(results: list[Any], language: str) -> str:
    """Return a readable plan failure summary without exposing raw result objects."""

    lines = [_message(language, "plan_failed")]
    for index, result in enumerate(results, start=1):
        if result.success:
            continue
        lines.append(
            "- "
            + _message(
                language,
                "failed_step",
                index=index,
                error=_friendly_error(result.error, language),
            )
        )
        break
    return "\n".join(lines)


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

    def __init__(
        self,
        cache: Any,
        user_id: int,
        agent_id: str,
        response_language: str = "pt-BR",
    ) -> None:
        self.cache = cache
        self.user_id = user_id
        self.agent_id = agent_id
        self.response_language = response_language

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
                    "description": "Revisar e confirmar plano de execução",
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
            _message(self.response_language, "plan_success")
            + "\n"
            + (
                _resource_summary(summary)
                if summary
                else _message(self.response_language, "no_resources")
            )
            if successful
            else _failure_summary(results, self.response_language)
        )
        self.cache.set(self._key(task_id), record, timeout=TASK_TTL)
        self.emit(
            task_id,
            "completed" if successful else "failed",
            _message(
                self.response_language,
                "plan_completed_event" if successful else "plan_failed_event",
            ),
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
