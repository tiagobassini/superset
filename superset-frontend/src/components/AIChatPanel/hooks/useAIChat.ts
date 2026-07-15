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

// TODO (Fase 2.4): implement useAIChat hook
// Central hook: sendMessage, confirmAction, cancelAction, history management.
// See docs/ai-integration/frontend-chat-sidebar.md for full specification.
import { SupersetClient } from '@superset-ui/core';
import { nanoid } from 'nanoid';
import { useCallback, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import type { RootState } from 'src/views/store';
import { addMessage, setLoading, setMessages, updatePendingAction } from '../store/aiChatSlice';
import type { ChatMessage, PendingAction } from '../store/types';
import { useAIContext } from './useAIContext';
import { loadHistory, saveHistory } from '../utils/sessionStorage';

type ChatResponse = { response?: string; pending_actions?: PendingAction[] };
type ConfirmResponse = { status?: PendingAction['status']; result?: unknown };

export const useAIChat = () => {
  const dispatch = useDispatch();
  const messages = useSelector((state: RootState) => state.aiChat.messages);
  const selectedAgentId = useSelector((state: RootState) => state.aiChat.selectedAgentId);
  const context = useAIContext();
  useEffect(() => { if (!messages.length) dispatch(setMessages(loadHistory())); }, [dispatch, messages.length]);
  useEffect(() => { saveHistory(messages); }, [messages]);
  const sendMessage = useCallback(async (content: string) => {
    const text = content.trim(); if (!text) return;
    const userMessage: ChatMessage = { id: nanoid(), role: 'user', content: text, timestamp: Date.now() };
    dispatch(addMessage(userMessage)); dispatch(setLoading(true));
    try {
      const { json } = await SupersetClient.post({ endpoint: '/api/v1/ai/chat', json: {
        message: text, agent_id: selectedAgentId ?? undefined, context,
        history: messages.map(({ role, content: previousContent }) => ({ role, content: previousContent })),
      } });
      const result = json as ChatResponse;
      dispatch(addMessage({ id: nanoid(), role: 'assistant', content: result.response ?? '', timestamp: Date.now(), pendingActions: result.pending_actions }));
    } finally { dispatch(setLoading(false)); }
  }, [context, dispatch, messages, selectedAgentId]);
  const cancelAction = useCallback((action: PendingAction) => dispatch(updatePendingAction({ ...action, status: 'cancelled' })), [dispatch]);
  const confirmAction = useCallback(async (action: PendingAction) => {
    dispatch(updatePendingAction({ ...action, status: 'confirmed' }));
    try {
      const { json } = await SupersetClient.post({ endpoint: '/api/v1/ai/confirm_action', json: { action_id: action.id, agent_id: selectedAgentId ?? undefined } });
      const result = json as ConfirmResponse;
      dispatch(updatePendingAction({ ...action, status: result.status ?? 'executed', result: result.result }));
    } catch { dispatch(updatePendingAction({ ...action, status: 'failed' })); }
  }, [dispatch, selectedAgentId]);
  return { messages, sendMessage, confirmAction, cancelAction };
};
