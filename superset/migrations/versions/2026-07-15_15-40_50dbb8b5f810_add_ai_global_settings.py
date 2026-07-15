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
"""Add global AI integration settings.

Revision ID: 50dbb8b5f810
Revises: 8c4e39a1d2f0
Create Date: 2026-07-15 15:40:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "50dbb8b5f810"
down_revision = "8c4e39a1d2f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_global_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sql_confirmation_mode", sa.String(32), nullable=False),
        sa.Column("sql_confirmation_role_ids", sa.JSON(), nullable=False),
        sa.Column("max_query_rows", sa.Integer(), nullable=False),
        sa.Column("history_storage", sa.String(32), nullable=False),
        sa.Column("history_retention_days", sa.Integer(), nullable=False),
        sa.Column("send_page_context", sa.Boolean(), nullable=False),
        sa.Column("include_datasets_in_prompt", sa.Boolean(), nullable=False),
        sa.Column("include_schema_in_prompt", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO ai_global_settings "
        "(id, sql_confirmation_mode, sql_confirmation_role_ids, max_query_rows, "
        "history_storage, history_retention_days, send_page_context, "
        "include_datasets_in_prompt, include_schema_in_prompt) "
        "VALUES (1, 'always', '[]', 1000, 'session', 30, 1, 1, 0)"
    )


def downgrade() -> None:
    op.drop_table("ai_global_settings")
