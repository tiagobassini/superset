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
AI Integration Plugin — Custom Exceptions
"""


class AIIntegrationError(Exception):
    """Base exception for the AI integration module."""


class AIProviderError(AIIntegrationError):
    """Raised when communication with an AI provider fails."""


class AIAgentNotFoundError(AIIntegrationError):
    """Raised when a requested AI agent does not exist or is inactive."""


class AIActionExpiredError(AIIntegrationError):
    """Raised when a pending action TTL has elapsed before confirmation."""


class AIPermissionError(AIIntegrationError):
    """Raised when the user lacks permission to use a specific tool or agent."""
