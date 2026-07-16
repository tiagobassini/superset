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
"""Add the derived AI metadata catalog.

Revision ID: 76c4a9e2d5b1
Revises: 3f2d9a7b6c10
Create Date: 2026-07-16 16:10:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "76c4a9e2d5b1"
down_revision = "3f2d9a7b6c10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_data_source_catalog",
        sa.Column("source_key", sa.String(length=1024), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("database_id", sa.Integer(), nullable=True),
        sa.Column("database_name", sa.String(length=256), nullable=True),
        sa.Column("schema", sa.String(length=256), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("related_names", sa.JSON(), nullable=False),
        sa.Column("normalized_terms", sa.JSON(), nullable=False),
        sa.Column("detected_languages", sa.JSON(), nullable=False),
        sa.Column("inferred_topics", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("source_key", name="pk_ai_data_source_catalog"),
    )
    op.create_index(
        "ix_ai_data_source_catalog_database_id",
        "ai_data_source_catalog",
        ["database_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_data_source_catalog_expires_at",
        "ai_data_source_catalog",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_data_source_catalog_expires_at", "ai_data_source_catalog")
    op.drop_index("ix_ai_data_source_catalog_database_id", "ai_data_source_catalog")
    op.drop_table("ai_data_source_catalog")
