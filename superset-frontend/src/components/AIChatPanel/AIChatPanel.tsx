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
import React from 'react';
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
 * TODO (Fase 2): implement full component tree:
 *   - ChatHeader
 *   - ModelSelector
 *   - MessageList / MessageBubble
 *   - ActionConfirmation
 *   - ContextBadge
 *   - ChatInput
 *   - ToggleButton
 */
const AIChatPanel: React.FC = () => { const dispatch = useDispatch(); const state = useSelector((root: RootState) => root.aiChat); const { agents } = useAgents(); const { messages, sendMessage } = useAIChat(); if (!state.isOpen) return <ToggleButton onClick={() => dispatch(setOpen(true))} />; return <aside role="complementary" aria-label="Assistente de IA"><ChatHeader onClose={() => dispatch(setOpen(false))} /><ModelSelector agents={agents} value={state.selectedAgentId} onChange={id => dispatch(setSelectedAgentId(id || null))} /><ContextBadge context={state.currentContext} /><MessageList messages={messages} /><ChatInput onSend={sendMessage} /></aside>; };

export default AIChatPanel;
