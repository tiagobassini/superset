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
import reducer, {
  addMessage,
  initialAIChatState,
  setCurrentContext,
  setOpen,
  updatePendingAction,
} from './aiChatSlice';

test('manages the chat state and pending actions', () => {
  const message = {
    id: 'message-1',
    role: 'assistant' as const,
    content: 'I can create this chart.',
    timestamp: 1,
    pendingActions: [
      {
        id: 'action-1',
        type: 'create_chart',
        description: 'Create chart',
        params: {},
        status: 'pending' as const,
      },
    ],
  };

  let state = reducer(initialAIChatState, setOpen(true));
  state = reducer(state, addMessage(message));
  state = reducer(
    state,
    setCurrentContext({ page: 'dashboard', resource_id: 42 }),
  );
  state = reducer(
    state,
    updatePendingAction({ ...message.pendingActions[0], status: 'cancelled' }),
  );

  expect(state.isOpen).toBe(true);
  expect(state.currentContext).toEqual({ page: 'dashboard', resource_id: 42 });
  expect(state.messages[0].pendingActions?.[0].status).toBe('cancelled');
});
