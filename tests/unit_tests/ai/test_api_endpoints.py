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
"""Behavior tests for the AI REST endpoint implementations."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Callable
from uuid import uuid4

import pytest
from flask import Response

from superset.ai import api
from superset.ai.exceptions import AIActionExpiredError, AIProviderError
from superset.ai.orchestrator import OrchestratorResult, PendingAction
from superset.ai.task_progress import AITaskProgress
from superset.ai.tools.base import ToolResult


class TaskCache:
    """Minimal cache implementation used to assert AI task transport behavior."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set(self, key: str, value: object, timeout: int) -> None:
        self.values[key] = value


def invoke(resource: object, name: str) -> Callable[[], Response | tuple[Response, int]]:
    """Invoke an endpoint body without FAB's authentication decorators."""
    return inspect.unwrap(getattr(type(resource), name)).__get__(resource, type(resource))


@pytest.fixture
def resource(monkeypatch: pytest.MonkeyPatch) -> api.AIRestApi:
    """Create an API resource with feature and permission guards already checked."""
    monkeypatch.setattr(api.AIRestApi, "_require_enabled", staticmethod(lambda: None))
    monkeypatch.setattr(api.AIRestApi, "_require", staticmethod(lambda _: None))
    return api.AIRestApi()


def agent(**overrides: Any) -> SimpleNamespace:
    """Return an agent shape sufficient for API serialization and authorization."""
    values = {
        "id": str(uuid4()),
        "name": "Local Ollama",
        "provider": "ollama",
        "model": "qwen3:1.7b",
        "is_default": True,
        "is_active": True,
        "base_url": "http://ollama:11434",
        "api_key_encrypted": None,
        "allowed_roles": [],
        "enabled_tools": None,
        "response_language": "pt-BR",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_chat_returns_response_and_pending_actions(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_agent = agent()
    pending = PendingAction(
        id=str(uuid4()),
        agent_id=configured_agent.id,
        type="create_dashboard",
        params={"dashboard_title": "Sales"},
        description="Create Sales",
    )
    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    monkeypatch.setattr(resource, "_can_use", lambda _: True)
    monkeypatch.setattr(
        api.AIOrchestrator,
        "chat",
        lambda *_: OrchestratorResult("I can create it.", [pending]),
    )
    with app.test_request_context(
        "/api/v1/ai/chat",
        method="POST",
        json={
            "message": "Create a dashboard",
            "history": [],
            "context": {"page": "other"},
        },
    ):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response = invoke(resource, "chat")()

    assert isinstance(response, Response)
    assert response.get_json()["response"] == "I can create it."
    assert response.get_json()["pending_actions"][0]["type"] == "create_dashboard"


def test_task_events_support_polling_and_sse_reconnection(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_agent = agent()
    cache = TaskCache()
    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    monkeypatch.setattr(resource, "_can_use", lambda _: True)
    monkeypatch.setattr(api, "cache_manager", SimpleNamespace(cache=cache))
    delayed: list[tuple[object, ...]] = []
    monkeypatch.setattr(api.run_ai_task, "delay", lambda *args: delayed.append(args))
    with app.test_request_context(
        "/api/v1/ai/tasks",
        method="POST",
        json={"message": "Analise vendas", "history": [], "context": {"page": "other"}},
    ):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response, status = invoke(resource, "create_task")()  # type: ignore[misc]

    task_id = response.get_json()["task_id"]
    assert status == 202
    assert delayed[0][0] == task_id
    progress = AITaskProgress(cache, 1, configured_agent.id)
    progress.emit(task_id, "analyzing", "Analisando", "analysis")
    progress.complete(task_id, OrchestratorResult("Análise pronta.", []))
    with app.test_request_context(
        f"/api/v1/ai/tasks/{task_id}?after=1",
        method="GET",
    ):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response = invoke(resource, "get_task")(task_id)
    assert [event["state"] for event in response.get_json()["events"]] == [
        "analyzing",
        "completed",
    ]

    with app.test_request_context(f"/api/v1/ai/tasks/{task_id}/events?after=2"):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response = invoke(resource, "task_events")(task_id)
    assert response.mimetype == "text/event-stream"
    assert "event: progress" in response.get_data(as_text=True)


def test_task_creation_is_audited_without_chat_content(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_agent = agent()
    events: list[dict[str, object]] = []
    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    monkeypatch.setattr(resource, "_can_use", lambda _: True)
    monkeypatch.setattr(api, "cache_manager", SimpleNamespace(cache=TaskCache()))
    monkeypatch.setattr(api.run_ai_task, "delay", lambda *_: None)
    monkeypatch.setattr("superset.extensions.event_logger.log", lambda **value: events.append(value))
    with app.test_request_context(
        "/api/v1/ai/tasks", method="POST", json={"message": "segredo", "context": {"page": "other"}}
    ):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        invoke(resource, "create_task")()

    assert events[0]["action"] == "ai_task_created"
    assert "segredo" not in str(events[0]["curated_payload"])


@pytest.mark.parametrize(
    ("exception", "status"),
    [(AIProviderError("unavailable"), 502), (None, 403)],
)
def test_chat_reports_provider_and_agent_access_errors(
    app: Any,
    resource: api.AIRestApi,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception | None,
    status: int,
) -> None:
    configured_agent = agent()
    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    monkeypatch.setattr(resource, "_can_use", lambda _: exception is not None)
    if exception:
        monkeypatch.setattr(api.AIOrchestrator, "chat", lambda *_: (_ for _ in ()).throw(exception))
    with app.test_request_context(
        "/api/v1/ai/chat", method="POST", json={"message": "hello", "context": {"page": "other"}}
    ):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response, actual_status = invoke(resource, "chat")()  # type: ignore[misc]

    assert actual_status == status
    assert response.get_json()["message"] in {
        "unavailable",
        "Seu perfil não tem permissão para usar o agente selecionado.",
    }


def test_chat_rejects_invalid_payload_and_unknown_agent(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.test_request_context("/api/v1/ai/chat", method="POST", json={}):
        response, status = invoke(resource, "chat")()  # type: ignore[misc]
    assert status == 400
    assert "message" in response.get_json()["message"]

    monkeypatch.setattr(resource, "_get_agent", lambda _: None)
    with app.test_request_context(
        "/api/v1/ai/chat", method="POST", json={"message": "hello", "context": {"page": "other"}}
    ):
        response, status = invoke(resource, "chat")()  # type: ignore[misc]
    assert status == 404
    assert response.get_json()["message"] == "Agent not found"


def test_confirm_action_returns_execution_and_expected_failures(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_agent = agent()
    action_id = str(uuid4())
    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    monkeypatch.setattr(resource, "_can_use", lambda _: True)
    monkeypatch.setattr(
        api.AIOrchestrator,
        "confirm_and_execute",
        lambda *_: ToolResult(True, {"id": 3}),
    )
    with app.test_request_context("/api/v1/ai/confirm_action", method="POST", json={"action_id": action_id}):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response = invoke(resource, "confirm_action")()
    assert isinstance(response, Response)
    assert response.get_json() == {"status": "executed", "result": {"id": 3}}

    monkeypatch.setattr(
        api.AIOrchestrator,
        "confirm_and_execute",
        lambda *_: ToolResult(False, None, "Tool access denied"),
    )
    with app.test_request_context("/api/v1/ai/confirm_action", method="POST", json={"action_id": action_id}):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response, status = invoke(resource, "confirm_action")()  # type: ignore[misc]
    assert status == 400
    assert response.get_json()["message"] == "Tool access denied"


def test_confirm_action_reports_expired_action(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_agent = agent()
    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    monkeypatch.setattr(resource, "_can_use", lambda _: True)
    monkeypatch.setattr(
        api.AIOrchestrator,
        "confirm_and_execute",
        lambda *_: (_ for _ in ()).throw(AIActionExpiredError("expired")),
    )
    with app.test_request_context("/api/v1/ai/confirm_action", method="POST", json={"action_id": str(uuid4())}):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response, status = invoke(resource, "confirm_action")()  # type: ignore[misc]
    assert status == 404
    assert response.get_json()["message"] == "expired"


def test_cancel_action_invalidates_pending_action_and_is_audited(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_agent = agent()
    events: list[dict[str, object]] = []
    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    monkeypatch.setattr(resource, "_can_use", lambda _: True)
    monkeypatch.setattr(api.AIOrchestrator, "cancel_pending_action", lambda *_: None)
    monkeypatch.setattr("superset.extensions.event_logger.log", lambda **value: events.append(value))
    with app.test_request_context(
        "/api/v1/ai/cancel_action", method="POST", json={"action_id": str(uuid4())}
    ):
        from flask import g

        g.user = SimpleNamespace(id=1, roles=[])
        response = invoke(resource, "cancel_action")()

    assert response.get_json() == {"status": "cancelled"}
    assert events[0]["action"] == "ai_action_cancelled"


def test_list_and_get_agents_honor_detail_mode(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_agent = agent()
    query = SimpleNamespace(
        order_by=lambda *_: SimpleNamespace(all=lambda: [configured_agent]),
        filter_by=lambda **_: [configured_agent],
    )
    monkeypatch.setattr(api.db, "session", SimpleNamespace(query=lambda *_: query))
    monkeypatch.setattr(resource, "_can_use", lambda _: True)
    with app.test_request_context("/api/v1/ai/agents"):
        response = invoke(resource, "list_agents")()
    assert isinstance(response, Response)
    assert response.get_json()["count"] == 1

    monkeypatch.setattr(resource, "_get_agent", lambda _: configured_agent)
    with app.test_request_context(f"/api/v1/ai/agents/{configured_agent.id}"):
        response = invoke(resource, "get_agent")("unused")
    assert isinstance(response, Response)
    assert response.get_json()["result"]["base_url"] == "http://ollama:11434"


def test_create_update_delete_agent_and_connection_test(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Administrator endpoints persist safe attributes and never return a secret."""
    created = agent()
    session = SimpleNamespace(
        add=lambda _: None,
        commit=lambda: None,
        delete=lambda _: None,
        get=lambda *_: None,
        query=lambda *_: SimpleNamespace(filter=lambda *_: SimpleNamespace(update=lambda *_1, **_2: None)),
    )
    monkeypatch.setattr(api.db, "session", session)
    monkeypatch.setattr(api, "AIAgent", lambda **_: created)
    monkeypatch.setattr(
        resource,
        "_agent_attributes",
        lambda payload: {**payload, "api_key_encrypted": None, "allowed_roles": []},
    )
    monkeypatch.setattr(resource, "_ensure_single_default", lambda _: None)
    monkeypatch.setattr(
        resource.agent_schema,
        "load",
        lambda _: {
            "name": "Local",
            "provider": "ollama",
            "model": "qwen",
            "base_url": "http://ollama:11434",
        },
    )
    with app.test_request_context("/api/v1/ai/agents", method="POST", json={"name": "Local"}):
        response, status = invoke(resource, "create_agent")()  # type: ignore[misc]
    assert status == 201
    assert response.get_json()["result"]["api_key_set"] is False

    monkeypatch.setattr(resource, "_get_agent", lambda _: created)
    with app.test_request_context(f"/api/v1/ai/agents/{created.id}", method="PUT", json={"name": "Updated"}):
        response = invoke(resource, "update_agent")(created.id)
    assert isinstance(response, Response)
    assert response.get_json()["result"]["name"] == "Local"

    with app.test_request_context(f"/api/v1/ai/agents/{created.id}", method="DELETE"):
        response = invoke(resource, "delete_agent")(created.id)
    assert isinstance(response, Response)
    assert response.get_json() == {"message": "Deleted"}

    monkeypatch.setattr(
        api.AIOrchestrator,
        "_build_provider",
        staticmethod(lambda _: SimpleNamespace(test_connection=lambda: True)),
    )
    with app.test_request_context(f"/api/v1/ai/agents/{created.id}/test", method="POST"):
        response = invoke(resource, "test_agent")(created.id)
    assert isinstance(response, Response)
    assert response.get_json() == {"success": True}


def test_global_settings_get_and_update_validate_roles(
    app: Any, resource: api.AIRestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SimpleNamespace(
        sql_confirmation_mode="all",
        sql_confirmation_role_ids=[],
        max_query_rows=100,
        history_storage="none",
        history_retention_days=30,
        send_page_context=True,
        include_datasets_in_prompt=True,
        include_schema_in_prompt=False,
    )
    session = SimpleNamespace(get=lambda *_: settings, add=lambda _: None, commit=lambda: None)
    monkeypatch.setattr(api.db, "session", session)
    monkeypatch.setattr(resource, "_serialize_global_settings", lambda *_: {"max_query_rows": 100})
    with app.test_request_context("/api/v1/ai/settings"):
        response = invoke(resource, "get_global_settings")()
    assert isinstance(response, Response)
    assert response.get_json() == {"result": {"max_query_rows": 100}}

    monkeypatch.setattr(resource.global_settings_schema, "load", lambda _: {"max_query_rows": 50})
    with app.test_request_context("/api/v1/ai/settings", method="PUT", json={"max_query_rows": 50}):
        response = invoke(resource, "update_global_settings")()
    assert isinstance(response, Response)
    assert response.get_json() == {"result": {"max_query_rows": 100}}
