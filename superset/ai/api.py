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
"""REST endpoints for the feature-flagged AI integration."""

from __future__ import annotations

from typing import Any

from flask import g, jsonify, request, Response
from flask_appbuilder.api import expose, protect, safe
from marshmallow import ValidationError

from superset import is_feature_enabled
from superset.ai.crypto import encrypt_api_key
from superset.ai.exceptions import AIActionExpiredError, AIProviderError
from superset.ai.models import AIAgent
from superset.ai.orchestrator import AIOrchestrator
from superset.ai.schemas import (
    AgentSchema,
    ChatRequestSchema,
    ConfirmActionRequestSchema,
)
from superset.ai.tools.registry import create_default_registry
from superset.extensions import db, security_manager
from superset.views.base_api import BaseSupersetApi, requires_json


class AIRestApi(BaseSupersetApi):
    """Expose chat, approval, and administrator agent-management endpoints."""

    resource_name = "ai"
    allow_browser_login = True
    class_permission_name = "AIAgentResource"
    chat_schema = ChatRequestSchema()
    confirm_schema = ConfirmActionRequestSchema()
    agent_schema = AgentSchema()

    @expose("/chat", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def chat(self) -> Response:
        """Send a message to an accessible agent."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            payload = self.chat_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        agent = self._get_agent(payload.get("agent_id"))
        if agent is None:
            return self._error("Agent not found", 404)
        if not agent.is_active or not self._can_use(agent):
            return self._error("Agent access denied", 403)
        try:
            result = AIOrchestrator(agent, create_default_registry(), g.user).chat(
                payload["message"], payload["history"], payload["context"]
            )
        except AIProviderError as ex:
            return self._error(str(ex), 502)
        return jsonify(
            {
                "response": result.response,
                "pending_actions": [
                    action.to_dict() for action in result.pending_actions
                ],
            }
        )

    @expose("/confirm_action", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def confirm_action(self) -> Response:
        """Execute a previously approved write action."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            payload = self.confirm_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        agent = self._get_agent(payload.get("agent_id"))
        if agent is None:
            return self._error("Agent not found", 404)
        if not agent.is_active or not self._can_use(agent):
            return self._error("Agent access denied", 403)
        try:
            result = AIOrchestrator(
                agent, create_default_registry(), g.user
            ).confirm_and_execute(str(payload["action_id"]))
        except AIActionExpiredError as ex:
            return self._error(str(ex), 404)
        if not result.success:
            return self._error(result.error or "Action failed", 400)
        return jsonify({"status": "executed", "result": result.data})

    @expose("/agents", methods=("GET",))
    @protect()
    @safe
    def list_agents(self) -> Response:
        """List accessible chat agents or every agent for an administrator."""
        self._require_enabled()
        include_inactive = request.args.get("include_inactive") == "true"
        if include_inactive:
            self._require("can_manage_ai_agents")
            agents = AIAgent.query.order_by(AIAgent.name).all()
            return jsonify(
                {
                    "count": len(agents),
                    "result": [
                        self._serialize_agent(agent, detailed=True) for agent in agents
                    ],
                }
            )
        self._require("can_use_ai_chat")
        agents = [
            agent
            for agent in AIAgent.query.filter_by(is_active=True)
            if self._can_use(agent)
        ]
        return jsonify(
            {
                "count": len(agents),
                "result": [self._serialize_agent(agent) for agent in agents],
            }
        )

    @expose("/agents/<string:agent_id>", methods=("GET",))
    @protect()
    @safe
    def get_agent(self, agent_id: str) -> Response:
        """Return administrator-only agent details without its API key."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        agent = self._get_agent(agent_id)
        return (
            jsonify({"result": self._serialize_agent(agent, detailed=True)})
            if agent
            else self._error("Agent not found", 404)
        )

    @expose("/agents", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def create_agent(self) -> Response:
        """Create an AI agent configuration."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        try:
            payload = self.agent_schema.load(request.json)
            required = {"name", "provider", "model"}
            if missing := required - payload.keys():
                return self._error(f"Missing fields: {', '.join(sorted(missing))}", 400)
            if payload["provider"] != "ollama" and "api_key" not in payload:
                return self._error("API key is required for cloud providers", 400)
            if payload["provider"] == "ollama" and not payload.get("base_url"):
                return self._error("Base URL is required for Ollama", 400)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        try:
            attributes = self._agent_attributes(payload)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        agent = AIAgent(**attributes)
        db.session.add(agent)
        self._ensure_single_default(agent)
        db.session.commit()
        return jsonify({"result": self._serialize_agent(agent, detailed=True)}), 201

    @expose("/agents/<string:agent_id>", methods=("PUT",))
    @protect()
    @safe
    @requires_json
    def update_agent(self, agent_id: str) -> Response:
        """Update a configuration while retaining omitted API keys."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        agent = self._get_agent(agent_id)
        if agent is None:
            return self._error("Agent not found", 404)
        try:
            payload = self.agent_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        try:
            attributes = self._agent_attributes(payload)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        for key, value in attributes.items():
            setattr(agent, key, value)
        self._ensure_single_default(agent)
        db.session.commit()
        return jsonify({"result": self._serialize_agent(agent, detailed=True)})

    @expose("/agents/<string:agent_id>", methods=("DELETE",))
    @protect()
    @safe
    def delete_agent(self, agent_id: str) -> Response:
        """Delete an agent configuration."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        agent = self._get_agent(agent_id)
        if agent is None:
            return self._error("Agent not found", 404)
        db.session.delete(agent)
        db.session.commit()
        return jsonify({"message": "Deleted"})

    @expose("/agents/<string:agent_id>/test", methods=("POST",))
    @protect()
    @safe
    def test_agent(self, agent_id: str) -> Response:
        """Test an agent endpoint without returning any secret."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        agent = self._get_agent(agent_id)
        if agent is None:
            return self._error("Agent not found", 404)
        try:
            ok = AIOrchestrator._build_provider(agent).test_connection()
        except Exception:  # pylint: disable=broad-except
            ok = False
        return jsonify({"success": ok})

    @staticmethod
    def _error(message: str, status: int) -> tuple[Response, int]:
        return jsonify({"message": message}), status

    @staticmethod
    def _require_enabled() -> None:
        if not is_feature_enabled("ENABLE_AI_INTEGRATION"):
            from werkzeug.exceptions import NotFound

            raise NotFound()

    @staticmethod
    def _require(permission: str) -> None:
        if not security_manager.can_access(permission, "AIAgentResource"):
            from werkzeug.exceptions import Forbidden

            raise Forbidden()

    def _get_agent(self, agent_id: Any) -> AIAgent | None:
        if agent_id:
            return db.session.get(AIAgent, str(agent_id))
        return AIAgent.query.filter_by(is_default=True, is_active=True).first()

    @staticmethod
    def _can_use(agent: AIAgent) -> bool:
        if not agent.allowed_roles:
            return True
        return bool(
            {role.id for role in agent.allowed_roles}
            & {role.id for role in g.user.roles}
        )

    @staticmethod
    def _serialize_agent(agent: AIAgent, detailed: bool = False) -> dict[str, Any]:
        result = {
            "id": agent.id,
            "name": agent.name,
            "provider": agent.provider,
            "model": agent.model,
            "is_default": agent.is_default,
            "is_active": agent.is_active,
        }
        if detailed:
            result.update(
                {
                    "base_url": agent.base_url,
                    "api_key_set": bool(agent.api_key_encrypted),
                    "role_ids": [role.id for role in agent.allowed_roles],
                    "enabled_tools": getattr(agent, "enabled_tools", None),
                }
            )
        return result

    @staticmethod
    def _agent_attributes(payload: dict[str, Any]) -> dict[str, Any]:
        attrs = {
            key: value
            for key, value in payload.items()
            if key not in {"api_key", "role_ids"}
        }
        if "api_key" in payload:
            attrs["api_key_encrypted"] = encrypt_api_key(payload["api_key"])
        if "role_ids" in payload:
            roles = security_manager.find_roles_by_id(payload["role_ids"])
            if len(roles) != len(payload["role_ids"]):
                raise ValidationError("One or more roles do not exist")
            attrs["allowed_roles"] = roles
        return attrs

    @staticmethod
    def _ensure_single_default(agent: AIAgent) -> None:
        """Clear the default marker from every other agent when requested."""
        if agent.is_default:
            AIAgent.query.filter(AIAgent.id != agent.id).update(
                {"is_default": False}, synchronize_session=False
            )
