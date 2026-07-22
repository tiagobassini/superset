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
"""
AI Integration Plugin — SQLAlchemy Models

Defines the AIAgent model (stored in the Superset database) and the
ai_agent_roles association table.

See docs/ai-integration/backend-api-tools.md for full specification.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import sqlalchemy as sa
from flask_appbuilder import Model
from flask_appbuilder.security.sqla.models import Role
from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Table, Text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import relationship

from superset import db

metadata = Model.metadata

# Supported AI providers. DeepSeek and Codex use the OpenAI-compatible adapter.
AI_PROVIDER_ENUM = Enum(
    "openai",
    "ollama",
    "anthropic",
    "deepseek",
    "codex",
    name="ai_provider",
)

# Association table: many-to-many between AIAgent and FAB Role.
# An agent can be restricted to specific roles; an empty set means all roles
# with `can_use_ai_chat` may use this agent.
ai_agent_roles = Table(
    "ai_agent_roles",
    metadata,
    Column("id", sa.Integer, primary_key=True),
    Column(
        "agent_id",
        String(36),
        nullable=False,
    ),
    Column(
        "role_id",
        sa.Integer,
        nullable=False,
    ),
)


class AIAgent(Model):
    """Represents an AI provider configuration (agent) within Superset.

    Each agent stores the connection details for one AI model endpoint
    (e.g. an OpenAI GPT-4o key, a local Ollama instance, or a DeepSeek
    endpoint).  The ``api_key_encrypted`` field is always stored as a
    Fernet-encrypted string — never plain-text.

    Roles listed in ``allowed_roles`` restrict which FAB roles may use this
    agent.  An empty list means any role that holds ``can_use_ai_chat`` can
    use it.
    """

    __tablename__ = "ai_agent"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name = Column(String(256), nullable=False)
    provider = Column(AI_PROVIDER_ENUM, nullable=False)
    model = Column(String(128), nullable=False)
    # Optional override URL — required for Ollama and self-hosted endpoints;
    # also used to point "openai" provider at DeepSeek/Codex APIs.
    base_url = Column(String(512), nullable=True)
    # API key encrypted at rest with the Superset SECRET_KEY (Fernet).
    # Never returned in API responses.
    api_key_encrypted = Column(Text, nullable=True)
    # When True, this agent is selected automatically when the user has not
    # picked one explicitly.
    is_default = Column(Boolean, default=False, nullable=False)
    # Soft-disable an agent without deleting it.
    is_active = Column(Boolean, default=True, nullable=False)
    # Language used by the provider when responding to the user.
    response_language = Column(String(16), default="pt-BR", nullable=False)
    enabled_tools = Column(sa.JSON, nullable=True)

    # Many-to-many: which FAB roles may use this agent.
    # Empty → any role with can_use_ai_chat may use it.
    allowed_roles = relationship(
        Role,
        secondary=ai_agent_roles,
        primaryjoin=lambda: AIAgent.id == ai_agent_roles.c.agent_id,
        secondaryjoin=lambda: Role.id == ai_agent_roles.c.role_id,
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<AIAgent {self.name!r} provider={self.provider} model={self.model}>"


class AIGlobalSettings(Model):
    """Singleton configuration controlling global AI integration behavior."""

    __tablename__ = "ai_global_settings"

    id = Column(Integer, primary_key=True, default=1)
    sql_confirmation_mode = Column(String(32), nullable=False, default="always")
    sql_confirmation_role_ids = Column(sa.JSON, nullable=False, default=list)
    max_query_rows = Column(Integer, nullable=False, default=1000)
    history_storage = Column(String(32), nullable=False, default="session")
    history_retention_days = Column(Integer, nullable=False, default=30)
    send_page_context = Column(Boolean, nullable=False, default=True)
    include_datasets_in_prompt = Column(Boolean, nullable=False, default=True)
    include_schema_in_prompt = Column(Boolean, nullable=False, default=False)


class AIDataSourceCatalogEntry(Model):
    """Derived, non-authoritative safe metadata for a discoverable source."""

    __tablename__ = "ai_data_source_catalog"

    source_key = Column(String(1024), primary_key=True)
    resource_type = Column(String(32), nullable=False)
    resource_id = Column(Integer, nullable=True)
    database_id = Column(Integer, nullable=True, index=True)
    database_name = Column(String(256), nullable=True)
    schema = Column(String(256), nullable=True)
    name = Column(String(512), nullable=False)
    description = Column(Text, nullable=False, default="")
    columns = Column(sa.JSON, nullable=False, default=list)
    related_names = Column(sa.JSON, nullable=False, default=list)
    is_virtual = Column(Boolean, nullable=False, default=False)
    normalized_terms = Column(sa.JSON, nullable=False, default=list)
    detected_languages = Column(sa.JSON, nullable=False, default=list)
    inferred_topics = Column(sa.JSON, nullable=False, default=list)
    version = Column(String(64), nullable=False)
    indexed_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    invalidated_at = Column(DateTime(timezone=True), nullable=True)


class AISemanticAssociation(Model):
    """Administrator-approved business vocabulary for source discovery."""

    __tablename__ = "ai_semantic_association"

    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    terms = Column(sa.JSON, nullable=False, default=list)
    source_name = Column(String(512), nullable=False)
    database_name = Column(String(256), nullable=True)
    schema = Column(String(256), nullable=True)
    metric_name = Column(String(256), nullable=True)
    dimension_mappings = Column(sa.JSON, nullable=False, default=dict)
    priority = Column(String(32), nullable=False, default="normal")
    is_active = Column(Boolean, nullable=False, default=True)
    extra = Column(sa.JSON, nullable=False, default=dict)


AI_GLOBAL_SETTINGS_DEFAULTS = {
    "sql_confirmation_mode": "always",
    "sql_confirmation_role_ids": [],
    "max_query_rows": 1000,
    "history_storage": "session",
    "history_retention_days": 30,
    "send_page_context": True,
    "include_datasets_in_prompt": True,
    "include_schema_in_prompt": False,
}


def get_ai_global_settings() -> AIGlobalSettings | Any:
    """Return the singleton settings row, falling back to secure defaults."""
    try:
        row = (
            db.session.execute(
                sa.select(AIGlobalSettings.__table__).where(
                    AIGlobalSettings.__table__.c.id == 1
                )
            )
            .mappings()
            .first()
        )
    except OperationalError:
        # Preserve the safe defaults while a deployment is awaiting migration.
        row = None
    if row is not None:
        return SimpleNamespace(**dict(row))
    return SimpleNamespace(id=1, **AI_GLOBAL_SETTINGS_DEFAULTS)
