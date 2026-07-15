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
import type { FC } from 'react';
import { styled } from '@apache-superset/core/theme';
import { useDispatch, useSelector } from 'react-redux';
import type { RootState } from 'src/views/store';
import { setOpen, setSelectedAgentId } from './store/aiChatSlice';
import { ToggleButton } from './components/ToggleButton';
import { ChatHeader } from './components/ChatHeader';
import { ModelSelector } from './components/ModelSelector';
import { ContextBadge } from './components/ContextBadge';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { useAgents } from './hooks/useAgents';
import { useAIChat } from './hooks/useAIChat';

/**
 * AIChatPanel — Floating AI assistant sidebar.
 *
 * Retractable right-side panel that lets authorized users interact with
 * AI providers to create charts, dashboards, run SQL queries, and more.
 *
 * See docs/ai-integration/frontend-chat-sidebar.md for full specification.
 *
 */
const Sidebar = styled.aside`
  background: ${({ theme }) => theme.colorBgContainer};
  border-left: 1px solid ${({ theme }) => theme.colorBorder};
  bottom: 0;
  box-shadow: ${({ theme }) => theme.boxShadowSecondary};
  display: flex;
  flex-direction: column;
  position: fixed;
  right: 0;
  top: 0;
  width: 380px;
  z-index: 1000;

  @media (max-width: 900px) {
    width: min(380px, 100vw);
  }
`;

const AIChatPanel: FC = () => {
  const dispatch = useDispatch();
  const state = useSelector((root: RootState) => root.aiChat);
  const { agents } = useAgents();
  const {
    messages,
    isLoading,
    sendMessage,
    confirmAction,
    cancelAction,
    clearChatHistory,
  } = useAIChat();

  if (!state.isOpen) {
    return <ToggleButton onClick={() => dispatch(setOpen(true))} />;
  }

  return (
    <Sidebar role="complementary" aria-label="Assistente de IA">
      <ChatHeader
        onClose={() => dispatch(setOpen(false))}
        onMinimize={() => dispatch(setOpen(false))}
      />
      <ModelSelector
        agents={agents}
        value={state.selectedAgentId}
        onChange={id => dispatch(setSelectedAgentId(id || null))}
      />
      <MessageList
        messages={messages}
        onConfirmAction={confirmAction}
        onCancelAction={cancelAction}
      />
      <ContextBadge context={state.currentContext} />
      <ChatInput
        disabled={isLoading}
        onClear={clearChatHistory}
        onSend={sendMessage}
      />
    </Sidebar>
  );
};

export default AIChatPanel;
