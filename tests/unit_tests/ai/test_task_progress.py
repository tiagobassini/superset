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
"""Tests for persisted AI task progress events."""

import pytest

from superset.ai.task_progress import AITaskProgress


class Cache:
    """In-memory cache implementing the task progress contract."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, timeout: int) -> None:
        self.values[key] = value


def test_task_events_are_ordered_and_reconnectable() -> None:
    progress = AITaskProgress(Cache(), 4, "agent-1")
    task_id = progress.create()
    progress.emit(task_id, "planning", "Planejando")
    progress.emit(task_id, "discovering", "Descobrindo")

    events = progress.events(task_id, after=1)

    assert events[0] == {
        "task_id": task_id,
        "sequence": 2,
        "state": "discovering",
        "message": "Descobrindo",
        "step": None,
        "data": None,
    }


def test_task_completion_uses_confirmation_or_clarification_state() -> None:
    from superset.ai.orchestrator import OrchestratorResult, PendingAction

    progress = AITaskProgress(Cache(), 4, "agent-1")
    confirmation_task = progress.create()
    clarification_task = progress.create()

    progress.complete(
        confirmation_task,
        OrchestratorResult(
            "",
            [
                PendingAction(
                    id="action",
                    agent_id="agent-1",
                    type="create_chart",
                    params={},
                    description="Criar gráfico",
                )
            ],
        ),
    )
    progress.complete(clarification_task, OrchestratorResult("Qual período deseja usar?", []))

    assert progress.events(confirmation_task)[0]["state"] == "awaiting_confirmation"
    assert progress.events(clarification_task)[0]["state"] == "awaiting_user_input"


def test_task_events_are_isolated_by_user_and_agent() -> None:
    cache = Cache()
    task_id = AITaskProgress(cache, 4, "agent-1").create()

    with pytest.raises(KeyError):
        AITaskProgress(cache, 5, "agent-1").events(task_id)
    with pytest.raises(KeyError):
        AITaskProgress(cache, 4, "agent-2").events(task_id)
