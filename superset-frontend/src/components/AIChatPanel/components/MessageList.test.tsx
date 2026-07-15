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
import { MessageList } from './MessageList';
import type { ChatMessage } from '../store/types';

test('renders confirmation cards and forwards user decisions for pending actions', () => {
  const onConfirmAction = jest.fn();
  const onCancelAction = jest.fn();
  const messages: ChatMessage[] = [
    {
      id: 'assistant-message',
      role: 'assistant',
      content: 'Posso criar o gráfico.',
      timestamp: 1,
      pendingActions: [
        {
          id: 'create-chart',
          type: 'create_chart',
          description: 'Criar gráfico de vendas',
          params: { chart_name: 'Vendas' },
          status: 'pending',
        },
      ],
    },
  ];

  render(
    <MessageList
      messages={messages}
      onCancelAction={onCancelAction}
      onConfirmAction={onConfirmAction}
    />,
  );

  expect(screen.getByText('Posso criar o gráfico.')).toBeInTheDocument();
  expect(screen.getByText('chart_name')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

  expect(onConfirmAction).toHaveBeenCalledWith('create-chart');
  expect(onCancelAction).toHaveBeenCalledWith('create-chart');
});

test('shows an action result link after a successful execution', () => {
  render(
    <MessageList
      messages={[
        {
          id: 'assistant-message',
          role: 'assistant',
          content: 'Pronto.',
          timestamp: 1,
          pendingActions: [
            {
              id: 'create-chart',
              type: 'create_chart',
              description: 'Criar gráfico',
              params: {},
              status: 'executed',
              result: { url: '/explore/?slice_id=1' },
            },
          ],
        },
      ]}
      onCancelAction={jest.fn()}
      onConfirmAction={jest.fn()}
    />,
  );

  expect(screen.getByRole('link', { name: 'Abrir recurso' })).toHaveAttribute(
    'href',
    '/explore/?slice_id=1',
  );
});
