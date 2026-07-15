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
import { fireEvent, render, screen } from 'spec/helpers/testing-library';
import { ChatInput } from './ChatInput';

test('sends a trimmed message with Ctrl+Enter and clears the input', () => {
  const onSend = jest.fn();
  render(<ChatInput onClear={jest.fn()} onSend={onSend} />);
  const input = screen.getByRole('textbox', { name: 'Mensagem para IA' });

  fireEvent.change(input, { target: { value: '  Criar gráfico  ' } });
  fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });

  expect(onSend).toHaveBeenCalledWith('Criar gráfico');
  expect(input).toHaveValue('');
});

test('clears both the input and persisted chat history on user request', () => {
  const onClear = jest.fn();
  render(<ChatInput onClear={onClear} onSend={jest.fn()} />);
  const input = screen.getByRole('textbox', { name: 'Mensagem para IA' });

  fireEvent.change(input, { target: { value: 'Mensagem' } });
  fireEvent.click(screen.getByRole('button', { name: 'Limpar' }));

  expect(onClear).toHaveBeenCalledTimes(1);
  expect(input).toHaveValue('');
});

test('moves focus to the textarea when requested by the chat panel', () => {
  render(<ChatInput autoFocus onClear={jest.fn()} onSend={jest.fn()} />);

  expect(
    screen.getByRole('textbox', { name: 'Mensagem para IA' }),
  ).toHaveFocus();
});
