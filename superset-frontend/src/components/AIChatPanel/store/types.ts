/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/**
 * TypeScript types and interfaces for the AIChatPanel.
 *
 * See docs/ai-integration/frontend-chat-sidebar.md for full specification.
 */

export type MessageRole = 'user' | 'assistant' | 'system';

export type ActionStatus =
  | 'pending'
  | 'confirmed'
  | 'cancelled'
  | 'executed'
  | 'failed';

export interface PendingAction {
  id: string;
  /** Tool name, e.g. 'create_chart', 'run_sql_query' */
  type: string;
  /** Human-readable description shown to the user before confirmation */
  description: string;
  params: Record<string, unknown>;
  status: ActionStatus;
  /** Populated after successful execution (e.g. { id, url }) */
  result?: unknown;
  /** Safe backend reason when the confirmed action could not be executed. */
  error?: string;
}

export interface ChatMessage {
  id: string;
  /** Server task identifier, retained in session history for reconnection. */
  taskId?: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  /** Actions returned by the AI that await user confirmation */
  pendingActions?: PendingAction[];
  isStreaming?: boolean;
  progressState?:
    | 'planning'
    | 'discovering'
    | 'analyzing'
    | 'awaiting_confirmation'
    | 'awaiting_user_input'
    | 'executing'
    | 'completed'
    | 'failed';
}

export interface AIAgent {
  id: string;
  name: string;
  provider: 'openai' | 'ollama' | 'deepseek' | 'anthropic' | 'codex';
  model: string;
  isDefault: boolean;
  isActive: boolean;
}

export interface PageContext {
  page: 'dashboard' | 'explore' | 'sqllab' | 'datasets' | 'charts' | 'other';
  resourceId?: number | string;
  resourceName?: string;
  metadata?: Record<string, unknown>;
}

export interface AIChatState {
  isOpen: boolean;
  messages: ChatMessage[];
  selectedAgentId: string | null;
  isLoading: boolean;
  currentContext: PageContext;
}
