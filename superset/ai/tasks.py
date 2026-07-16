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
"""Celery execution for reconnectable AI analytics tasks."""

from __future__ import annotations

from typing import Any

from flask import current_app

from superset.ai.audit import audit_task
from superset.ai.exceptions import AIProviderError
from superset.ai.execution_plan import ExecutionPlanService, PlannedAction
from superset.ai.models import AIAgent
from superset.ai.orchestrator import AIOrchestrator
from superset.ai.task_progress import AITaskProgress
from superset.ai.tools.registry import create_default_registry
from superset.extensions import cache_manager, celery_app, db, security_manager
from superset.utils.core import override_user


@celery_app.task(name="ai.run_task")
def run_ai_task(
    task_id: str, agent_id: str, user_id: int, payload: dict[str, Any]
) -> None:
    """Run an AI request out of band while publishing safe progress events."""
    progress = AITaskProgress(cache_manager.cache, user_id, agent_id)
    agent = db.session.get(AIAgent, agent_id)
    user = security_manager.get_user_by_id(user_id)
    if agent is None or user is None or not agent.is_active:
        progress.emit(task_id, "failed", "O agente não está mais disponível.", "access")
        audit_task("ai_task_blocked", user_id, task_id, agent_id)
        return
    allowed_roles = {role.id for role in agent.allowed_roles}
    user_roles = {role.id for role in user.roles}
    if allowed_roles and not allowed_roles.intersection(user_roles):
        progress.emit(task_id, "failed", "Você não tem acesso a este agente.", "access")
        audit_task("ai_task_blocked", user_id, task_id, agent_id)
        return
    progress.emit(
        task_id, "discovering", "Procurando fontes de dados acessíveis.", "discovery"
    )
    progress.emit(task_id, "analyzing", "Analisando as fontes encontradas.", "analysis")
    try:
        # Tool permissions use ``g.user``; Celery has an app context but no
        # request context unless it is explicitly established here.
        with current_app.test_request_context():
            with override_user(user):
                result = AIOrchestrator(agent, create_default_registry(), user).chat(
                    payload["message"],
                    payload.get("history", []),
                    payload.get("context", {}),
                )
    except AIProviderError:
        progress.emit(
            task_id, "failed", "Não foi possível obter uma resposta da IA.", "provider"
        )
        audit_task("ai_task_failed", user_id, task_id, agent_id)
        return
    except Exception:  # pylint: disable=broad-except
        progress.emit(
            task_id,
            "failed",
            "Não foi possível concluir a tarefa da IA.",
            "execution",
        )
        audit_task("ai_task_failed", user_id, task_id, agent_id)
        return
    progress.complete(task_id, result)
    audit_task("ai_task_completed", user_id, task_id, agent_id)


@celery_app.task(name="ai.run_plan_task")
def run_ai_plan_task(task_id: str, plan_id: str, agent_id: str, user_id: int) -> None:
    """Execute an approved plan while exposing each completed step to chat."""
    progress = AITaskProgress(cache_manager.cache, user_id, agent_id)
    agent = db.session.get(AIAgent, agent_id)
    user = security_manager.get_user_by_id(user_id)
    if agent is None or user is None:
        progress.emit(task_id, "failed", "O agente não está mais disponível.", "access")
        return
    progress.emit(task_id, "executing", "Executando o plano aprovado.", "execution")
    try:
        with current_app.test_request_context():
            with override_user(user):
                def on_step(
                    index: int, action: PlannedAction, result: Any
                ) -> None:
                    progress.emit(
                        task_id,
                        "executing",
                        f"Etapa {index}: {action.tool_name} "
                        f"{'concluída' if result.success else 'falhou'}.",
                        action.tool_name,
                        result.to_dict(),
                    )

                results = ExecutionPlanService(
                    create_default_registry(), user, agent_id, cache_manager.cache
                ).confirm_and_execute(plan_id, on_step)
    except Exception:  # pylint: disable=broad-except
        progress.emit(
            task_id, "failed", "Não foi possível executar o plano.", "execution"
        )
        return
    progress.complete_plan(task_id, results)
