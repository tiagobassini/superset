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

export type AIProvider =
  | 'anthropic'
  | 'codex'
  | 'deepseek'
  | 'ollama'
  | 'openai';

export interface AIAgentConfiguration {
  api_key_set?: boolean;
  base_url?: string | null;
  id: string;
  is_active: boolean;
  is_default: boolean;
  model: string;
  name: string;
  provider: AIProvider;
  role_ids?: number[];
  enabled_tools?: string[] | null;
}

export type AIAgentUpdate = Partial<
  Pick<
    AIAgentConfiguration,
    | 'base_url'
    | 'enabled_tools'
    | 'is_active'
    | 'is_default'
    | 'model'
    | 'name'
    | 'provider'
  >
> & {
  api_key?: string;
  role_ids?: number[];
};

export interface AIGlobalSettings {
  history_retention_days: number;
  history_storage: 'database' | 'session';
  include_datasets_in_prompt: boolean;
  include_schema_in_prompt: boolean;
  max_query_rows: number;
  send_page_context: boolean;
  sql_confirmation_mode: 'always' | 'roles_only';
  sql_confirmation_role_ids: number[];
}
