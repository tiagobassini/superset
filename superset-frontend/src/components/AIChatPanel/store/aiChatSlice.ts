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

// TODO (Fase 2.1): implement Redux slice for AIChatPanel state
// See docs/ai-integration/frontend-chat-sidebar.md for full specification.
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type {
  AIChatState,
  ChatMessage,
  PageContext,
  PendingAction,
} from './types';

export const initialAIChatState: AIChatState = {
  isOpen: false,
  messages: [],
  selectedAgentId: null,
  isLoading: false,
  currentContext: { page: 'other' },
};

const aiChatSlice = createSlice({
  name: 'aiChat',
  initialState: initialAIChatState,
  reducers: {
    setOpen(state, action: PayloadAction<boolean>) {
      state.isOpen = action.payload;
    },
    toggleOpen(state) {
      state.isOpen = !state.isOpen;
    },
    setMessages(state, action: PayloadAction<ChatMessage[]>) {
      state.messages = action.payload;
    },
    addMessage(state, action: PayloadAction<ChatMessage>) {
      state.messages.push(action.payload);
    },
    updateMessage(state, action: PayloadAction<ChatMessage>) {
      const index = state.messages.findIndex(
        message => message.id === action.payload.id,
      );
      if (index >= 0) {
        state.messages[index] = action.payload;
      }
    },
    updatePendingAction(state, action: PayloadAction<PendingAction>) {
      state.messages.forEach(message => {
        const actionIndex = message.pendingActions?.findIndex(
          pendingAction => pendingAction.id === action.payload.id,
        );
        if (actionIndex !== undefined && actionIndex >= 0) {
          message.pendingActions![actionIndex] = action.payload;
        }
      });
    },
    setSelectedAgentId(state, action: PayloadAction<string | null>) {
      state.selectedAgentId = action.payload;
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.isLoading = action.payload;
    },
    setCurrentContext(state, action: PayloadAction<PageContext>) {
      state.currentContext = action.payload;
    },
    clearMessages(state) {
      state.messages = [];
    },
  },
});

export const {
  addMessage,
  clearMessages,
  setCurrentContext,
  setLoading,
  setMessages,
  setOpen,
  setSelectedAgentId,
  toggleOpen,
  updateMessage,
  updatePendingAction,
} = aiChatSlice.actions;

export default aiChatSlice.reducer;
