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

import type { ChatMessage } from '../store/types';

const STORAGE_KEY = 'superset_ai_chat_history';

/** Maximum number of messages kept in sessionStorage to avoid bloat. */
const MAX_HISTORY_SIZE = 100;

/**
 * Persists the chat message history to sessionStorage.
 * Trims to the last MAX_HISTORY_SIZE messages before saving.
 *
 * Architecture note: sessionStorage is the initial storage strategy.
 * To migrate to server-side persistence, replace this module's
 * save/load with calls to POST/GET /api/v1/ai/history — the hook
 * interface remains the same.
 */
export const saveHistory = (messages: ChatMessage[]): void => {
  try {
    const trimmed = messages.slice(-MAX_HISTORY_SIZE);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // sessionStorage may be unavailable (private mode, storage full, etc.)
  }
};

/** Loads the chat message history from sessionStorage. */
export const loadHistory = (): ChatMessage[] => {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
};

/** Clears the chat message history from sessionStorage. */
export const clearHistory = (): void => {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
};
