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
"""Unit tests for AI REST request validation and response secrecy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import g
from marshmallow import ValidationError
from werkzeug.exceptions import Forbidden

from superset.ai.api import AIRestApi
from superset.ai.orchestrator import PendingAction
from superset.ai.schemas import (
    AgentSchema,
    ChatRequestSchema,
    ConfirmActionRequestSchema,
    GlobalAISettingsSchema,
)


def test_chat_request_schema_accepts_safe_history_and_context() -> None:
    payload = ChatRequestSchema().load(
        {
            "message": "List datasets",
            "agent_id": "123e4567-e89b-12d3-a456-426614174000",
            "context": {"page": "dashboard", "resource_id": 1, "metadata": {}},
            "history": [{"role": "user", "content": "Hello"}],
        }
    )

    assert payload["context"]["page"] == "dashboard"
    assert payload["history"][0]["role"] == "user"


def test_chat_request_schema_rejects_provider_only_history_roles() -> None:
    with pytest.raises(ValidationError):
        ChatRequestSchema().load(
            {
                "message": "hello",
                "context": {"page": "other"},
                "history": [{"role": "tool", "content": "untrusted"}],
            }
        )


def test_confirm_action_schema_requires_a_uuid() -> None:
    with pytest.raises(ValidationError):
        ConfirmActionRequestSchema().load({"action_id": "not-a-uuid"})


def test_agent_schema_keeps_roles_absent_on_update() -> None:
    payload = AgentSchema().load({"name": "Updated agent"})

    assert "role_ids" not in payload


def test_agent_schema_rejects_unsupported_provider() -> None:
    with pytest.raises(ValidationError):
        AgentSchema().load({"provider": "unsupported"})


def test_agent_schema_accepts_openai_compatible_providers() -> None:
    payload = AgentSchema().load({"provider": "deepseek"})

    assert payload["provider"] == "deepseek"


def test_agent_schema_validates_response_language() -> None:
    payload = AgentSchema().load({"response_language": "pt-BR"})

    assert payload["response_language"] == "pt-BR"
    with pytest.raises(ValidationError):
        AgentSchema().load({"response_language": "de-DE"})


def test_agent_schema_accepts_docker_service_base_url() -> None:
    payload = AgentSchema().load({"base_url": "http://ollama:11434"})

    assert payload["base_url"] == "http://ollama:11434"


@pytest.mark.parametrize("base_url", ["ollama:11434", "ftp://ollama:11434"])
def test_agent_schema_rejects_non_http_base_url(base_url: str) -> None:
    with pytest.raises(ValidationError):
        AgentSchema().load({"base_url": base_url})


def test_global_settings_schema_enforces_safe_limits() -> None:
    payload = GlobalAISettingsSchema().load(
        {"sql_confirmation_mode": "roles_only", "max_query_rows": 1000}
    )

    assert payload["sql_confirmation_mode"] == "roles_only"
    with pytest.raises(ValidationError):
        GlobalAISettingsSchema().load({"max_query_rows": 0})


def test_agent_serialization_never_exposes_encrypted_api_key() -> None:
    agent = SimpleNamespace(
        id="agent-1",
        name="Production",
        provider="openai",
        model="gpt-4o",
        is_default=True,
        is_active=True,
        base_url=None,
        api_key_encrypted="secret-ciphertext",
        allowed_roles=[SimpleNamespace(id=3)],
        enabled_tools=["list_datasets"],
    )

    result = AIRestApi._serialize_agent(agent, detailed=True)

    assert result["api_key_set"] is True
    assert "api_key_encrypted" not in result
    assert "secret-ciphertext" not in result.values()
    assert result["enabled_tools"] == ["list_datasets"]


def test_pending_action_response_hides_internal_agent_binding() -> None:
    action = PendingAction(
        id="action-1",
        agent_id="agent-1",
        type="create_chart",
        params={"slice_name": "Sales"},
        description="Create chart",
    )

    result = action.to_dict()

    assert result["type"] == "create_chart"
    assert result["status"] == "pending"
    assert "agent_id" not in result


def test_permission_denial_is_audited(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blocked AI endpoint access must be visible in Superset's audit trail."""
    from superset.ai import api

    events: list[dict[str, object]] = []
    monkeypatch.setattr(api.security_manager, "can_access", lambda *_: False)
    monkeypatch.setattr(
        "superset.extensions.event_logger.log", lambda **payload: events.append(payload)
    )
    with app.test_request_context("/api/v1/ai/agents"):
        g.user = SimpleNamespace(id=9)
        with pytest.raises(Forbidden):
            AIRestApi._require("can_manage_ai_agents")

    assert events[0]["action"] == "ai_authorization_denied"
