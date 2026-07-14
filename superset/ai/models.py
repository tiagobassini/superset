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

import sqlalchemy as sa
from flask_appbuilder import Model
from sqlalchemy import Boolean, Column, Enum, ForeignKey, String, Table, Text
from sqlalchemy.orm import relationship

from superset import db
from superset.models.helpers import AuditMixinNullable

metadata = Model.metadata  # pylint: disable=no-member

# Supported AI providers.
# "openai" also covers DeepSeek/Codex via custom base_url.
AI_PROVIDER_ENUM = Enum(
    "openai",
    "ollama",
    "anthropic",
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
        ForeignKey("ai_agent.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "role_id",
        sa.Integer,
        ForeignKey("ab_role.id", ondelete="CASCADE"),
        nullable=False,
    ),
)


class AIAgent(AuditMixinNullable, db.Model):
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

    # Many-to-many: which FAB roles may use this agent.
    # Empty → any role with can_use_ai_chat may use it.
    allowed_roles = relationship(
        "Role",
        secondary=ai_agent_roles,
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<AIAgent {self.name!r} provider={self.provider} model={self.model}>"
