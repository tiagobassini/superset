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
import { useEffect, useRef } from 'react';
import { styled } from '@apache-superset/core/theme';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '../store/types';

const List = styled.div`
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  min-height: 0;
  overflow-y: auto;
  padding: ${({ theme }) => theme.sizeUnit * 3}px;
`;

export interface MessageListProps {
  messages: ChatMessage[];
  onConfirmAction: (actionId: string) => void;
  onCancelAction: (actionId: string) => void;
}

/** Scrollable, live-updated list of chat messages. */
export const MessageList = ({
  messages,
  onConfirmAction,
  onCancelAction,
}: MessageListProps) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof endRef.current?.scrollIntoView === 'function') {
      endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages]);

  return (
    <List aria-live="polite" aria-label="Mensagens do assistente de IA">
      {messages.map(message => (
        <MessageBubble
          key={message.id}
          message={message}
          onConfirmAction={onConfirmAction}
          onCancelAction={onCancelAction}
        />
      ))}
      <div ref={endRef} />
    </List>
  );
};
