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
"""add ai_agent and ai_agent_roles tables

Revision ID: 33c72567c98a
Revises: 4b2a8c9d3e1f
Create Date: 2026-07-14 18:22:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "33c72567c98a"
down_revision = "4b2a8c9d3e1f"


def upgrade() -> None:
    # Create the ai_agent table.
    # The provider column uses a VARCHAR instead of a native ENUM so that
    # it works identically across SQLite (dev), PostgreSQL, and MySQL —
    # the application layer enforces the allowed values.
    op.create_table(
        "ai_agent",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_on", sa.DateTime(), nullable=True),
        sa.Column("changed_on", sa.DateTime(), nullable=True),
        sa.Column(
            "created_by_fk",
            sa.Integer(),
            sa.ForeignKey("ab_user.id", name="fk_ai_agent_created_by_fk_ab_user"),
            nullable=True,
        ),
        sa.Column(
            "changed_by_fk",
            sa.Integer(),
            sa.ForeignKey("ab_user.id", name="fk_ai_agent_changed_by_fk_ab_user"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_agent"),
    )

    # Create the ai_agent_roles association table.
    op.create_table(
        "ai_agent_roles",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ai_agent.id", name="fk_ai_agent_roles_agent_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("ab_role.id", name="fk_ai_agent_roles_role_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_agent_roles"),
    )


def downgrade() -> None:
    op.drop_table("ai_agent_roles")
    op.drop_table("ai_agent")
