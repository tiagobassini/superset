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
import { applicationRoot } from 'src/utils/getBootstrapData';
import { ActionConfirmation } from './ActionConfirmation';
import type { ChatMessage } from '../store/types';

const MARKDOWN_LINK_PATTERN = /\[([^\]]+)\]\((\/[^)\s]+)\)/g;

const resolveInternalUrl = (url: string) => {
  const root = applicationRoot();
  if (!root || root === '/' || url.startsWith(`${root}/`)) {
    return url;
  }
  return `${root}${url}`;
};

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

const TypingIndicator = styled.span`
  align-items: center;
  display: inline-flex;
  gap: ${({ theme }) => theme.sizeUnit}px;

  span {
    animation: ai-typing 1.2s infinite ease-in-out;
    background: ${({ theme }) => theme.colorPrimary};
    border-radius: 50%;
    height: ${({ theme }) => theme.sizeUnit}px;
    width: ${({ theme }) => theme.sizeUnit}px;
  }

  span:nth-of-type(2) {
    animation-delay: 0.15s;
  }

  span:nth-of-type(3) {
    animation-delay: 0.3s;
  }

  @keyframes ai-typing {
    0%,
    80%,
    100% {
      opacity: 0.35;
      transform: scale(0.8);
    }

    40% {
      opacity: 1;
      transform: scale(1.2);
    }
  }
`;

const MessageContent = styled.div`
  white-space: pre-wrap;
  overflow-wrap: anywhere;

  a {
    font-weight: ${({ theme }) => theme.fontWeightStrong};
  }
`;

const renderMessageContent = (content: string) => {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(MARKDOWN_LINK_PATTERN)) {
    const [raw, label, url] = match;
    const index = match.index ?? 0;
    if (index > lastIndex) {
      parts.push(content.slice(lastIndex, index));
    }
    parts.push(
      <a key={`${url}-${index}`} href={resolveInternalUrl(url)}>
        {label}
      </a>,
    );
    lastIndex = index + raw.length;
  }

  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }

  return parts.length > 0 ? parts : content;
};

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
    <MessageContent>{renderMessageContent(message.content)}</MessageContent>
    {message.isStreaming && (
      <TypingIndicator aria-label="A IA está respondendo" role="status">
        <span />
        <span />
        <span />
      </TypingIndicator>
    )}
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
