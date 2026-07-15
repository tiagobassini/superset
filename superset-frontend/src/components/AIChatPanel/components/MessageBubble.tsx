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
import { styled } from '@apache-superset/core/theme';
import { ActionConfirmation } from './ActionConfirmation';
import type { ChatMessage } from '../store/types';

const Bubble = styled.article<{ $role: ChatMessage['role'] }>`
  align-self: ${({ $role }) => ($role === 'user' ? 'flex-end' : 'flex-start')};
  background: ${({ theme, $role }) =>
    $role === 'user' ? theme.colorPrimaryBg : theme.colorFillQuaternary};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: ${({ theme }) => theme.borderRadiusLG}px;
  max-width: 92%;
  padding: ${({ theme }) => theme.sizeUnit * 2}px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
`;

const Sender = styled.div`
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  margin-bottom: ${({ theme }) => theme.sizeUnit}px;
`;

export interface MessageBubbleProps {
  message: ChatMessage;
  onConfirmAction: (actionId: string) => void;
  onCancelAction: (actionId: string) => void;
}

/** Renders a chat message and its optional confirmation cards. */
export const MessageBubble = ({
  message,
  onConfirmAction,
  onCancelAction,
}: MessageBubbleProps) => (
  <Bubble $role={message.role} aria-label={`Mensagem ${message.role}`}>
    <Sender>{message.role === 'user' ? 'Você' : 'Assistente de IA'}</Sender>
    {message.content || (message.isStreaming && 'Digitando…')}
    {message.pendingActions?.map(action => (
      <ActionConfirmation
        key={action.id}
        action={action}
        onConfirm={onConfirmAction}
        onCancel={onCancelAction}
      />
    ))}
  </Bubble>
);
