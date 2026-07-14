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
AI Integration Plugin — Tool Registry

Central registry that maps tool names to AITool instances.
The Orchestrator queries the registry to get the list of tools available
for a given agent/user, which is then passed to the AI provider.

See docs/ai-integration/backend-api-tools.md for full specification.
"""
# TODO (Fase 1.4): implement ToolRegistry and all AITool subclasses
