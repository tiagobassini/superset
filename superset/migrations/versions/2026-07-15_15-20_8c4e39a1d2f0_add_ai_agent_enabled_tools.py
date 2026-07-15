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
"""Add enabled tools to AI agents.

Revision ID: 8c4e39a1d2f0
Revises: 33c72567c98a
Create Date: 2026-07-15 15:20:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "8c4e39a1d2f0"
down_revision = "33c72567c98a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_agent", sa.Column("enabled_tools", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_agent", "enabled_tools")
