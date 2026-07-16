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
import {
  clearHistory,
  loadHistory,
  saveHistory,
} from '../utils/sessionStorage';

type TaskEvent = {
  state: ChatMessage['progressState'];
  message: string;
  sequence: number;
};
type ChatResponse = {
  task_id?: string;
  status?: ChatMessage['progressState'];
  response?: string;
  pending_actions?: PendingAction[];
  events?: TaskEvent[];
};
type ConfirmResponse = { status?: PendingAction['status']; result?: unknown };

const errorMessage = async (error: unknown) => {
  if (error instanceof Response) {
    try {
      const body = (await error.clone().json()) as { message?: unknown };
      if (typeof body.message === 'string') return body.message;
    } catch {
      return `A solicitação foi recusada (${error.status}).`;
    }
  }
  if (error instanceof Error && error.message) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    const { message } = error as { message?: unknown };
    if (typeof message === 'string') return message;
  }
  return 'Não foi possível executar a ação.';
};

const isTerminalTaskState = (state?: ChatMessage['progressState']) =>
  state === 'awaiting_confirmation' ||
  state === 'awaiting_user_input' ||
  state === 'completed' ||
  state === 'failed';

const toHistory = (messages: ChatMessage[]) =>
  messages.flatMap(message => {
    if (message.role !== 'user' && message.role !== 'assistant') return [];
    const actionResults = (message.pendingActions ?? [])
      .filter(
        action => action.status === 'executed' || action.status === 'failed',
      )
      .map(action => ({
        role: 'assistant' as const,
        content:
          action.status === 'executed'
            ? `Confirmed action ${action.type} executed: ${JSON.stringify(action.result ?? {})}`
            : `Confirmed action ${action.type} failed: ${action.error ?? 'Unknown error'}`,
      }));
    return [{ role: message.role, content: message.content }, ...actionResults];
  });

export const useAIChat = () => {
  const dispatch = useDispatch();
  const messages = useSelector((state: RootState) => state.aiChat.messages);
  const selectedAgentId = useSelector(
    (state: RootState) => state.aiChat.selectedAgentId,
  );
  const context = useAIContext();
  const [isHistoryLoaded, setHistoryLoaded] = useState(false);
  useEffect(() => {
    dispatch(setMessages(loadHistory()));
    setHistoryLoaded(true);
  }, [dispatch]);
  useEffect(() => {
    if (isHistoryLoaded) saveHistory(messages);
  }, [isHistoryLoaded, messages]);
  const sendMessage = useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text) return;
      const userMessage: ChatMessage = {
        id: nanoid(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
      };
      const responseMessage: ChatMessage = {
        id: nanoid(),
        role: 'assistant',
        content: 'Planejando a análise.',
        timestamp: Date.now(),
        isStreaming: true,
        progressState: 'planning',
      };
      dispatch(addMessage(userMessage));
      dispatch(addMessage(responseMessage));
      dispatch(setLoading(true));
      try {
        const { json } = await SupersetClient.post({
          endpoint: '/api/v1/ai/tasks',
          jsonPayload: {
            message: text,
            agent_id: selectedAgentId ?? undefined,
            context,
            history: toHistory(messages),
          },
          stringify: false,
        });
        const result = json as ChatResponse;
        let latestEvent = result.events?.[result.events.length - 1];
        let latestResult = result;
        while (result.task_id && !isTerminalTaskState(latestResult.status)) {
          dispatch(
            updateMessage({
              ...responseMessage,
              content: latestEvent?.message ?? 'Planejando a análise.',
              isStreaming: true,
              progressState: latestEvent?.state ?? 'planning',
              taskId: result.task_id,
            }),
          );
          await new Promise(resolve => window.setTimeout(resolve, 750));
          const { json: taskJson } = await SupersetClient.get({
            endpoint: `/api/v1/ai/tasks/${result.task_id}?agent_id=${selectedAgentId ?? ''}&after=${latestEvent?.sequence ?? 0}`,
          });
          latestResult = taskJson as ChatResponse;
          latestEvent = latestResult.events?.[latestResult.events.length - 1] ?? latestEvent;
        }
        const state = latestResult.status ?? latestEvent?.state;
        dispatch(
          updateMessage({
            ...responseMessage,
            content: latestResult.response ?? latestEvent?.message ?? '',
            isStreaming: !isTerminalTaskState(state),
            progressState: state,
            pendingActions: latestResult.pending_actions,
            taskId: result.task_id,
          }),
        );
      } catch (error) {
        dispatch(
          updateMessage({
            ...responseMessage,
            content: await errorMessage(error),
            isStreaming: false,
          }),
        );
      } finally {
        dispatch(setLoading(false));
      }
    },
    [context, dispatch, messages, selectedAgentId],
  );
  const getAction = useCallback(
    (actionId: string) =>
      messages
        .flatMap((message: ChatMessage) => message.pendingActions ?? [])
        .find((action: PendingAction) => action.id === actionId),
    [messages],
  );
  const cancelAction = useCallback(
    async (actionId: string) => {
      const action = getAction(actionId);
      if (action?.status === 'pending') {
        try {
          await SupersetClient.post({
            endpoint: '/api/v1/ai/cancel_action',
            jsonPayload: { action_id: action.id, agent_id: selectedAgentId ?? undefined },
            stringify: false,
          });
        } catch {
          return;
        }
        dispatch(updatePendingAction({ ...action, status: 'cancelled' }));
      }
    },
    [dispatch, getAction, selectedAgentId],
  );
  const confirmAction = useCallback(
    async (actionId: string) => {
      const action = getAction(actionId);
      if (!action || action.status !== 'pending') return;
      dispatch(updatePendingAction({ ...action, status: 'confirmed' }));
      try {
        const { json } = await SupersetClient.post({
          endpoint: '/api/v1/ai/confirm_action',
          jsonPayload: {
            action_id: action.id,
            agent_id: selectedAgentId ?? undefined,
          },
          stringify: false,
        });
        const result = json as ConfirmResponse;
        dispatch(
          updatePendingAction({
            ...action,
            status: result.status ?? 'executed',
            result: result.result,
          }),
        );
      } catch (error) {
        dispatch(
          updatePendingAction({
            ...action,
            status: 'failed',
            error: await errorMessage(error),
          }),
        );
      }
    },
    [dispatch, getAction, selectedAgentId],
  );
  const clearChatHistory = useCallback(() => {
    clearHistory();
    dispatch(clearMessages());
  }, [dispatch]);
  return {
    messages,
    isLoading: useSelector((state: RootState) => state.aiChat.isLoading),
    sendMessage,
    confirmAction,
    cancelAction,
    clearChatHistory,
  };
};
