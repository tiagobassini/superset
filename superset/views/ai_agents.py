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
"""SPA entry point for the AI agent settings page."""

from flask_appbuilder import expose, permission_name
from flask_appbuilder.security.decorators import has_access

from superset.superset_typing import FlaskResponse
from superset.views.base import BaseSupersetView


class AIAgentsSettingsView(BaseSupersetView):
    """Render the agent settings SPA only for AI settings administrators."""

    route_base = "/settings/ai"
    class_permission_name = "AIAgentResource"

    @expose("/agents")
    @has_access
    @permission_name("can_manage_ai_agents")
    def agents(self) -> FlaskResponse:
        """Serve the frontend route for managing AI agents."""
        return super().render_app_template()
