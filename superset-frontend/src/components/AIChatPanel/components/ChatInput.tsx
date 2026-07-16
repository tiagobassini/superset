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
import { useState } from 'react';
import { styled } from '@apache-superset/core/theme';
import { Button, Input } from '@superset-ui/core/components';

const Container = styled.div`
  border-top: 1px solid ${({ theme }) => theme.colorBorder};
  padding: ${({ theme }) => theme.sizeUnit * 2}px;
`;

const Controls = styled.div`
  display: flex;
  justify-content: flex-end;
  margin-top: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export interface ChatInputProps {
  autoFocus?: boolean;
  disabled?: boolean;
  onSend: (text: string) => void;
}

/** Input for a chat message; Ctrl+Enter sends without losing multiline support. */
export const ChatInput = ({
  autoFocus = false,
  disabled = false,
  onSend,
}: ChatInputProps) => {
  const [text, setText] = useState('');
  const send = () => {
    const content = text.trim();
    if (!content || disabled) return;
    onSend(content);
    setText('');
  };

  return (
    <Container>
      <Input.TextArea
        aria-label="Mensagem para IA"
        autoFocus={autoFocus}
        autoSize={{ minRows: 2, maxRows: 6 }}
        disabled={disabled}
        onChange={event => setText(event.target.value)}
        onKeyDown={event => {
          if (event.ctrlKey && event.key === 'Enter') {
            event.preventDefault();
            send();
          }
        }}
        placeholder="Digite sua mensagem…"
        value={text}
      />
      <Controls>
        <Button
          buttonSize="small"
          disabled={!text.trim() || disabled}
          onClick={send}
        >
          Enviar
        </Button>
      </Controls>
    </Container>
  );
};
