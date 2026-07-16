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
from superset.ai.audit import audit_task
from superset.ai.crypto import encrypt_api_key
from superset.ai.discovery import AnalyticsDiscoveryService, build_discovery_query
from superset.ai.exceptions import AIActionExpiredError, AIProviderError
from superset.ai.execution_plan import ExecutionPlanService
from superset.ai.metadata_catalog import MetadataCatalogService
from superset.ai.models import AIAgent, AIGlobalSettings, get_ai_global_settings
from superset.ai.orchestrator import AIOrchestrator
from superset.ai.schemas import (
    AgentSchema,
    ChatRequestSchema,
    ConfirmActionRequestSchema,
    ConfirmPlanRequestSchema,
    GlobalAISettingsSchema,
)
from superset.ai.task_progress import AITaskProgress
from superset.ai.tasks import run_ai_plan_task, run_ai_task
from superset.ai.tools.registry import create_default_registry
from superset.extensions import cache_manager, db, security_manager
from superset.utils import json
from superset.views.base_api import BaseSupersetApi, requires_json


class AIRestApi(BaseSupersetApi):
    """Expose chat, approval, and administrator agent-management endpoints."""

    resource_name = "ai"
    allow_browser_login = True
    class_permission_name = "AIAgentResource"
    method_permission_name = {
        "chat": "use_ai_chat",
        "confirm_action": "use_ai_chat",
        "cancel_action": "use_ai_chat",
        "confirm_plan": "use_ai_chat",
        "cancel_plan": "use_ai_chat",
        "create_task": "use_ai_chat",
        "get_task": "use_ai_chat",
        "task_events": "use_ai_chat",
        "list_agents": "use_ai_chat",
        "get_global_settings": "manage_ai_agents",
        "update_global_settings": "manage_ai_agents",
        "get_agent": "manage_ai_agents",
        "create_agent": "manage_ai_agents",
        "update_agent": "manage_ai_agents",
        "delete_agent": "manage_ai_agents",
        "test_agent": "manage_ai_agents",
        "rebuild_metadata_catalog": "manage_ai_agents",
        "invalidate_metadata_catalog": "manage_ai_agents",
    }
    chat_schema = ChatRequestSchema()
    confirm_schema = ConfirmActionRequestSchema()
    confirm_plan_schema = ConfirmPlanRequestSchema()
    agent_schema = AgentSchema()
    global_settings_schema = GlobalAISettingsSchema()

    @expose("/settings", methods=("GET",))
    @protect()
    @safe
    def get_global_settings(self) -> Response:
        """Return global AI preferences to an authorized administrator."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        return jsonify({"result": self._serialize_global_settings()})

    @expose("/settings", methods=("PUT",))
    @protect()
    @safe
    @requires_json
    def update_global_settings(self) -> Response:
        """Persist validated global AI preferences."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        try:
            payload = self.global_settings_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        if "sql_confirmation_role_ids" in payload:
            roles = security_manager.find_roles_by_id(
                payload["sql_confirmation_role_ids"]
            )
            if len(roles) != len(payload["sql_confirmation_role_ids"]):
                return self._error("One or more roles do not exist", 400)
        settings = db.session.get(AIGlobalSettings, 1)
        if settings is None:
            settings = AIGlobalSettings(id=1)
            db.session.add(settings)
        for key, value in payload.items():
            setattr(settings, key, value)
        db.session.commit()
        return jsonify({"result": self._serialize_global_settings(settings)})

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
        if error := self._validate_agent_access(agent):
            return error
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
        if error := self._validate_agent_access(agent):
            return error
        audit_task(
            "ai_action_confirmed", g.user.id, str(payload["action_id"]), str(agent.id)
        )
        try:
            result = AIOrchestrator(
                agent, create_default_registry(), g.user
            ).confirm_and_execute(str(payload["action_id"]))
        except AIActionExpiredError as ex:
            audit_task(
                "ai_action_failed", g.user.id, str(payload["action_id"]), str(agent.id)
            )
            return self._error(str(ex), 404)
        if not result.success:
            audit_task(
                "ai_action_failed", g.user.id, str(payload["action_id"]), str(agent.id)
            )
            return self._error(result.error or "Action failed", 400)
        audit_task(
            "ai_action_completed", g.user.id, str(payload["action_id"]), str(agent.id)
        )
        return jsonify({"status": "executed", "result": result.data})

    @expose("/cancel_action", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def cancel_action(self) -> Response:
        """Invalidate a pending action after the user declines its confirmation."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            payload = self.confirm_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        agent = self._get_agent(payload.get("agent_id"))
        if agent is None:
            return self._error("Agent not found", 404)
        if error := self._validate_agent_access(agent):
            return error
        try:
            AIOrchestrator(
                agent, create_default_registry(), g.user
            ).cancel_pending_action(str(payload["action_id"]))
        except AIActionExpiredError as ex:
            return self._error(str(ex), 404)
        audit_task(
            "ai_action_cancelled", g.user.id, str(payload["action_id"]), str(agent.id)
        )
        return jsonify({"status": "cancelled"})

    @expose("/confirm_plan", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def confirm_plan(self) -> Response:
        """Execute a previously presented immutable analytics plan once."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            payload = self.confirm_plan_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        agent = self._get_agent(payload.get("agent_id"))
        if agent is None:
            return self._error("Agent not found", 404)
        if error := self._validate_agent_access(agent):
            return error
        try:
            progress = AITaskProgress(cache_manager.cache, g.user.id, str(agent.id))
            progress.snapshot(str(payload["task_id"]))
        except KeyError:
            return self._error("Task not found", 404)
        run_ai_plan_task.delay(
            str(payload["task_id"]),
            str(payload["action_id"]),
            str(agent.id),
            g.user.id,
        )
        return jsonify(progress.snapshot(str(payload["task_id"]))), 202

    @expose("/cancel_plan", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def cancel_plan(self) -> Response:
        """Cancel an immutable plan before any write is started."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            payload = self.confirm_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        agent = self._get_agent(payload.get("agent_id"))
        if agent is None:
            return self._error("Agent not found", 404)
        if error := self._validate_agent_access(agent):
            return error
        try:
            ExecutionPlanService(
                create_default_registry(), g.user, str(agent.id), cache_manager.cache
            ).cancel(str(payload["action_id"]))
        except AIActionExpiredError as ex:
            return self._error(str(ex), 404)
        return jsonify({"status": "cancelled"})

    @expose("/tasks", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def create_task(self) -> Response:
        """Run an AI request while recording reconnectable progress events."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            payload = self.chat_schema.load(request.json)
        except ValidationError as ex:
            return self._error(str(ex), 400)
        agent = self._get_agent(payload.get("agent_id"))
        if agent is None:
            return self._error("Agent not found", 404)
        if error := self._validate_agent_access(agent):
            return error
        progress = AITaskProgress(cache_manager.cache, g.user.id, str(agent.id))
        task_id = progress.create()
        progress.emit(task_id, "planning", "Planejando a análise.", "plan")
        audit_task("ai_task_created", g.user.id, task_id, str(agent.id))
        run_ai_task.delay(task_id, str(agent.id), g.user.id, payload)
        return jsonify(progress.snapshot(task_id)), 202

    @expose("/tasks/<string:task_id>", methods=("GET",))
    @protect()
    @safe
    def get_task(self, task_id: str) -> Response:
        """Return persisted progress events, supporting polling after reload."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            task = self._get_task_snapshot(task_id)
        except (KeyError, ValueError):
            return self._error("Task not found", 404)
        return jsonify(task)

    @expose("/tasks/<string:task_id>/events", methods=("GET",))
    @protect()
    @safe
    def task_events(self, task_id: str) -> Response:
        """Expose task events as an SSE-compatible one-shot reconnect response."""
        self._require_enabled()
        self._require("can_use_ai_chat")
        try:
            events = self._get_task_events(task_id)
        except (KeyError, ValueError):
            return self._error("Task not found", 404)
        body = "".join(
            f"id: {event['sequence']}\nevent: progress\ndata: {json.dumps(event)}\n\n"
            for event in events
        )
        return Response(
            body,
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def _get_task_events(self, task_id: str) -> list[dict[str, Any]]:
        """Read task events after the requested cursor for polling or SSE recovery."""
        agent = self._get_agent(request.args.get("agent_id"))
        if agent is None or not self._can_use(agent):
            raise KeyError("Agent access denied")
        after = int(request.args.get("after", 0))
        return AITaskProgress(cache_manager.cache, g.user.id, str(agent.id)).events(
            task_id, after
        )

    def _get_task_snapshot(self, task_id: str) -> dict[str, Any]:
        """Read the current public task state for the polling fallback."""
        agent = self._get_agent(request.args.get("agent_id"))
        if agent is None or not self._can_use(agent):
            raise KeyError("Agent access denied")
        after = int(request.args.get("after", 0))
        return AITaskProgress(cache_manager.cache, g.user.id, str(agent.id)).snapshot(
            task_id, after
        )

    @expose("/agents", methods=("GET",))
    @protect()
    @safe
    def list_agents(self) -> Response:
        """List accessible chat agents or every agent for an administrator."""
        self._require_enabled()
        include_inactive = request.args.get("include_inactive") == "true"
        if include_inactive:
            self._require("can_manage_ai_agents")
            agents = db.session.query(AIAgent).order_by(AIAgent.name).all()
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
            for agent in db.session.query(AIAgent).filter_by(is_active=True)
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

    @expose("/catalog/rebuild", methods=("POST",))
    @protect()
    @safe
    def rebuild_metadata_catalog(self) -> Response:
        """Rebuild the derived metadata index from live authorized metadata."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        catalog = MetadataCatalogService()
        catalog.invalidate()
        result = AnalyticsDiscoveryService(g.user, catalog=catalog).discover(
            build_discovery_query("metadata catalog")
        )
        return jsonify(
            {
                "indexed": sum(result.searched.values()),
                "searched": dict(result.searched),
                "catalog": dict(result.catalog_stats or {}),
                "latency_ms": result.latency_ms,
            }
        )

    @expose("/catalog/invalidate", methods=("POST",))
    @protect()
    @safe
    @requires_json
    def invalidate_metadata_catalog(self) -> Response:
        """Invalidate source or database entries after an administrative sync."""
        self._require_enabled()
        self._require("can_manage_ai_agents")
        payload = request.json or {}
        source_key = payload.get("source_key")
        database_id = payload.get("database_id")
        if source_key is not None and not isinstance(source_key, str):
            return self._error("source_key must be a string", 400)
        if database_id is not None and not isinstance(database_id, int):
            return self._error("database_id must be an integer", 400)
        if source_key is None and database_id is None:
            return self._error("source_key or database_id is required", 400)
        invalidated = MetadataCatalogService().invalidate(
            source_key=source_key, database_id=database_id
        )
        return jsonify({"invalidated": invalidated})

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

            from superset.extensions import event_logger

            event_logger.log(
                user_id=getattr(getattr(g, "user", None), "id", None),
                action="ai_authorization_denied",
                dashboard_id=None,
                duration_ms=None,
                slice_id=None,
                referrer=None,
                curated_payload={"permission": permission},
                curated_form_data=None,
            )

            raise Forbidden()

    def _get_agent(self, agent_id: Any) -> AIAgent | None:
        if agent_id:
            return db.session.get(AIAgent, str(agent_id))
        return (
            db.session.query(AIAgent).filter_by(is_default=True, is_active=True).first()
        )

    def _validate_agent_access(self, agent: AIAgent) -> tuple[Response, int] | None:
        """Return a safe, actionable access error for a selected AI agent."""
        if not agent.is_active:
            return self._error("O agente selecionado está inativo.", 409)
        if not self._can_use(agent):
            return self._error(
                "Seu perfil não tem permissão para usar o agente selecionado.", 403
            )
        return None

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
                    "response_language": getattr(agent, "response_language", "pt-BR"),
                    "role_ids": [role.id for role in agent.allowed_roles],
                    "enabled_tools": getattr(agent, "enabled_tools", None),
                }
            )
        return result

    @staticmethod
    def _serialize_global_settings(
        settings: AIGlobalSettings | None = None,
    ) -> dict[str, Any]:
        settings = settings or get_ai_global_settings()
        return {
            "sql_confirmation_mode": settings.sql_confirmation_mode,
            "sql_confirmation_role_ids": settings.sql_confirmation_role_ids,
            "max_query_rows": settings.max_query_rows,
            "history_storage": settings.history_storage,
            "history_retention_days": settings.history_retention_days,
            "send_page_context": settings.send_page_context,
            "include_datasets_in_prompt": settings.include_datasets_in_prompt,
            "include_schema_in_prompt": settings.include_schema_in_prompt,
        }

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
            db.session.query(AIAgent).filter(AIAgent.id != agent.id).update(
                {"is_default": False}, synchronize_session=False
            )
