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
import { SupersetClient } from '@superset-ui/core';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { act, render, waitFor } from 'spec/helpers/testing-library';
import reducer from '../store/aiChatSlice';
import type { ChatMessage } from '../store/types';
import { useAIChat } from './useAIChat';

jest.mock('./useAIContext', () => ({
  useAIContext: () => ({ page: 'other' }),
}));

const createWrapper = () => {
  const store = configureStore({ reducer: { aiChat: reducer } });
  let chat: ReturnType<typeof useAIChat> | undefined;
  const Harness = () => {
    chat = useAIChat();
    return null;
  };
  render(
    <Provider store={store}>
      <Harness />
    </Provider>,
  );
  return { store, getChat: () => chat! };
};

beforeEach(() => {
  jest.useRealTimers();
  sessionStorage.clear();
  jest.restoreAllMocks();
});

afterEach(() => {
  jest.useRealTimers();
});

test('sends history and replaces the loading response with the AI response', async () => {
  const post = jest.spyOn(SupersetClient, 'post').mockResolvedValue({
    json: { response: 'Resposta', pending_actions: [] },
  } as never);
  const { getChat } = createWrapper();

  await act(async () => getChat().sendMessage('Olá'));

  expect(post).toHaveBeenCalledWith(
    expect.objectContaining({
      endpoint: '/api/v1/ai/tasks',
      jsonPayload: expect.objectContaining({ message: 'Olá', history: [] }),
    }),
  );
  expect(
    getChat().messages.map((message: ChatMessage) => message.content),
  ).toEqual(['Olá', 'Resposta']);
  expect(getChat().isLoading).toBe(false);
});

test('shows an assistant error message when chat request fails', async () => {
  jest.spyOn(SupersetClient, 'post').mockRejectedValue(new Error('offline'));
  const { getChat } = createWrapper();

  await act(async () => getChat().sendMessage('Olá'));

  expect(getChat().messages[1].content).toBe('offline');
});

test('confirms and cancels pending actions by id', async () => {
  sessionStorage.setItem(
    'superset_ai_chat_history',
    JSON.stringify([
      {
        id: 'message',
        role: 'assistant',
        content: 'Ação',
        timestamp: 1,
        pendingActions: [
          {
            id: 'confirm',
            type: 'create_chart',
            description: 'Criar',
            params: {},
            status: 'pending',
          },
          {
            id: 'cancel',
            type: 'run_sql_query',
            description: 'Cancelar',
            params: {},
            status: 'pending',
          },
        ],
      },
    ]),
  );
  const { getChat } = createWrapper();
  jest.spyOn(SupersetClient, 'post').mockResolvedValue({
    json: { status: 'executed', result: { id: 1 } },
  } as never);
  await waitFor(() => expect(getChat().messages).toHaveLength(1));
  await act(async () => getChat().confirmAction('confirm'));
  expect(getChat().messages[0].pendingActions?.[0].status).toBe('executed');
  await act(async () => getChat().cancelAction('cancel'));
  expect(getChat().messages[0].pendingActions?.[1].status).toBe('cancelled');
});

test('keeps polling a confirmed execution plan after the first awaiting snapshot', async () => {
  jest.useFakeTimers();
  sessionStorage.setItem(
    'superset_ai_chat_history',
    JSON.stringify([
      {
        id: 'message',
        role: 'assistant',
        content: 'Plano pronto',
        timestamp: 1,
        taskId: 'task-id',
        progressState: 'awaiting_confirmation',
        pendingActions: [
          {
            id: 'plan-id',
            type: 'execution_plan',
            description: 'Revisar e confirmar plano de execução',
            params: { task_id: 'task-id' },
            status: 'pending',
          },
        ],
      },
    ]),
  );
  jest.spyOn(SupersetClient, 'post').mockResolvedValue({
    json: {
      task_id: 'task-id',
      status: 'awaiting_confirmation',
      response: 'Plano pronto',
      pending_actions: [
        {
          id: 'plan-id',
          type: 'execution_plan',
          description: 'Revisar e confirmar plano de execução',
          params: { task_id: 'task-id' },
          status: 'pending',
        },
      ],
      events: [],
    },
  } as never);
  jest.spyOn(SupersetClient, 'get').mockResolvedValue({
    json: {
      task_id: 'task-id',
      status: 'completed',
      response: 'Plano concluído.',
      pending_actions: [],
      events: [
        { state: 'completed', message: 'Plano concluído.', sequence: 2 },
      ],
    },
  } as never);
  const { getChat } = createWrapper();

  await waitFor(() => expect(getChat().messages).toHaveLength(1));
  await act(async () => {
    const confirmation = getChat().confirmAction('plan-id');
    await Promise.resolve();
    jest.advanceTimersByTime(750);
    await confirmation;
  });

  expect(SupersetClient.get).toHaveBeenCalled();
  expect(getChat().messages[0]).toMatchObject({
    content: 'Plano concluído.',
    progressState: 'completed',
    pendingActions: [],
  });
});

test('keeps the backend failure reason for the next assistant request', async () => {
  sessionStorage.setItem(
    'superset_ai_chat_history',
    JSON.stringify([
      {
        id: 'message',
        role: 'assistant',
        content: 'Ação',
        timestamp: 1,
        pendingActions: [
          {
            id: 'confirm',
            type: 'create_dataset',
            description: 'Criar dataset',
            params: {},
            status: 'pending',
          },
        ],
      },
    ]),
  );
  const post = jest
    .spyOn(SupersetClient, 'post')
    .mockRejectedValueOnce(new Error('Dataset parameters are invalid.'))
    .mockResolvedValueOnce({
      json: { response: 'Entendi', pending_actions: [] },
    } as never);
  const { getChat } = createWrapper();

  await waitFor(() => expect(getChat().messages).toHaveLength(1));
  await act(async () => getChat().confirmAction('confirm'));
  await act(async () => getChat().sendMessage('Por que falhou?'));

  expect(getChat().messages[0].pendingActions?.[0]).toMatchObject({
    status: 'failed',
    error: 'Dataset parameters are invalid.',
  });
  expect(post).toHaveBeenLastCalledWith(
    expect.objectContaining({
      endpoint: '/api/v1/ai/tasks',
      jsonPayload: expect.objectContaining({
        history: expect.arrayContaining([
          expect.objectContaining({
            content: expect.stringContaining('Dataset parameters are invalid.'),
          }),
        ]),
      }),
    }),
  );
});
