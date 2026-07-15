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
import { useCallback, useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import type { RootState } from 'src/views/store';
import {
  addMessage,
  clearMessages,
  setLoading,
  setMessages,
  updateMessage,
  updatePendingAction,
} from '../store/aiChatSlice';
import type { ChatMessage, PendingAction } from '../store/types';
import { useAIContext } from './useAIContext';
import { clearHistory, loadHistory, saveHistory } from '../utils/sessionStorage';

type ChatResponse = { response?: string; pending_actions?: PendingAction[] };
type ConfirmResponse = { status?: PendingAction['status']; result?: unknown };

const toHistory = (messages: ChatMessage[]) =>
  messages
    .filter(message => message.role === 'user' || message.role === 'assistant')
    .map(message => ({ role: message.role, content: message.content }));

export const useAIChat = () => {
  const dispatch = useDispatch();
  const messages = useSelector((state: RootState) => state.aiChat.messages);
  const selectedAgentId = useSelector((state: RootState) => state.aiChat.selectedAgentId);
  const context = useAIContext();
  const [isHistoryLoaded, setHistoryLoaded] = useState(false);
  useEffect(() => {
    dispatch(setMessages(loadHistory()));
    setHistoryLoaded(true);
  }, [dispatch]);
  useEffect(() => {
    if (isHistoryLoaded) saveHistory(messages);
  }, [isHistoryLoaded, messages]);
  const sendMessage = useCallback(async (content: string) => {
    const text = content.trim(); if (!text) return;
    const userMessage: ChatMessage = { id: nanoid(), role: 'user', content: text, timestamp: Date.now() };
    const responseMessage: ChatMessage = {
      id: nanoid(), role: 'assistant', content: '', timestamp: Date.now(), isStreaming: true,
    };
    dispatch(addMessage(userMessage));
    dispatch(addMessage(responseMessage));
    dispatch(setLoading(true));
    try {
      const { json } = await SupersetClient.post({ endpoint: '/api/v1/ai/chat', jsonPayload: {
        message: text, agent_id: selectedAgentId ?? undefined, context,
        history: toHistory(messages),
      }, stringify: false });
      const result = json as ChatResponse;
      dispatch(updateMessage({
        ...responseMessage,
        content: result.response ?? '',
        isStreaming: false,
        pendingActions: result.pending_actions,
      }));
    } catch {
      dispatch(updateMessage({
        ...responseMessage,
        content: 'Não foi possível obter uma resposta da IA. Tente novamente.',
        isStreaming: false,
      }));
    } finally { dispatch(setLoading(false)); }
  }, [context, dispatch, messages, selectedAgentId]);
  const getAction = useCallback((actionId: string) => messages
    .flatMap((message: ChatMessage) => message.pendingActions ?? [])
    .find((action: PendingAction) => action.id === actionId), [messages]);
  const cancelAction = useCallback((actionId: string) => {
    const action = getAction(actionId);
    if (action?.status === 'pending') {
      dispatch(updatePendingAction({ ...action, status: 'cancelled' }));
    }
  }, [dispatch, getAction]);
  const confirmAction = useCallback(async (actionId: string) => {
    const action = getAction(actionId);
    if (!action || action.status !== 'pending') return;
    dispatch(updatePendingAction({ ...action, status: 'confirmed' }));
    try {
      const { json } = await SupersetClient.post({ endpoint: '/api/v1/ai/confirm_action', jsonPayload: { action_id: action.id, agent_id: selectedAgentId ?? undefined }, stringify: false });
      const result = json as ConfirmResponse;
      dispatch(updatePendingAction({ ...action, status: result.status ?? 'executed', result: result.result }));
    } catch { dispatch(updatePendingAction({ ...action, status: 'failed' })); }
  }, [dispatch, getAction, selectedAgentId]);
  const clearChatHistory = useCallback(() => {
    clearHistory();
    dispatch(clearMessages());
  }, [dispatch]);
  return { messages, isLoading: useSelector((state: RootState) => state.aiChat.isLoading), sendMessage, confirmAction, cancelAction, clearChatHistory };
};
