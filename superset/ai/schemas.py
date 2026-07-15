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
"""Request validation schemas for the AI REST API."""

from marshmallow import fields, Schema, validate


class PageContextSchema(Schema):
    """Safe subset of the page information used by the system prompt."""

    page = fields.String(required=True, validate=validate.Length(max=100))
    resource_id = fields.Raw(allow_none=True)
    resource_name = fields.String(allow_none=True, validate=validate.Length(max=200))
    metadata = fields.Dict(keys=fields.String(), values=fields.Raw(), load_default=dict)


class ChatHistorySchema(Schema):
    """A provider-neutral conversation message accepted from the client."""

    role = fields.String(required=True, validate=validate.OneOf(["user", "assistant"]))
    content = fields.String(required=True, validate=validate.Length(max=10000))


class ChatRequestSchema(Schema):
    """Validate a chat request before any provider is contacted."""

    message = fields.String(required=True, validate=validate.Length(min=1, max=10000))
    agent_id = fields.UUID(allow_none=True)
    context = fields.Nested(PageContextSchema, required=True)
    history = fields.List(fields.Nested(ChatHistorySchema), load_default=list)


class ConfirmActionRequestSchema(Schema):
    """Validate an explicit approval for a pending action."""

    action_id = fields.UUID(required=True)
    agent_id = fields.UUID(allow_none=True)


class AgentSchema(Schema):
    """Validate agent create and update payloads without exposing secrets."""

    name = fields.String(validate=validate.Length(min=1, max=256))
    provider = fields.String(
        validate=validate.OneOf(
            ["openai", "ollama", "anthropic", "deepseek", "codex"]
        )
    )
    model = fields.String(validate=validate.Length(min=1, max=128))
    base_url = fields.URL(allow_none=True)
    api_key = fields.String(load_only=True, validate=validate.Length(min=1, max=4096))
    is_default = fields.Boolean()
    is_active = fields.Boolean()
    role_ids = fields.List(fields.Integer())
    enabled_tools = fields.List(fields.String(validate=validate.Length(min=1, max=128)))


class GlobalAISettingsSchema(Schema):
    """Validate the administrator-managed AI integration preferences."""

    sql_confirmation_mode = fields.String(
        validate=validate.OneOf(["always", "roles_only"])
    )
    sql_confirmation_role_ids = fields.List(fields.Integer())
    max_query_rows = fields.Integer(validate=validate.Range(min=1, max=100000))
    history_storage = fields.String(validate=validate.OneOf(["session", "database"]))
    history_retention_days = fields.Integer(validate=validate.Range(min=1, max=3650))
    send_page_context = fields.Boolean()
    include_datasets_in_prompt = fields.Boolean()
    include_schema_in_prompt = fields.Boolean()
