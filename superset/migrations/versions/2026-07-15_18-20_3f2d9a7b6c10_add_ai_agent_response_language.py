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
"""Add the configured response language to AI agents.

Revision ID: 3f2d9a7b6c10
Revises: 50dbb8b5f810
Create Date: 2026-07-15 18:20:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "3f2d9a7b6c10"
down_revision = "50dbb8b5f810"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_agent",
        sa.Column(
            "response_language",
            sa.String(length=16),
            nullable=False,
            server_default="pt-BR",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_agent", "response_language")
