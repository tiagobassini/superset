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
import { SupersetClient } from '@superset-ui/core';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from 'spec/helpers/testing-library';
import type { AgentsListProps } from './components/AgentsList';
import AIAgentsSettings from './AIAgentsSettings';

const mockUpdateAgent = jest.fn();

jest.mock('src/features/home/SubMenu', () => () => <div />);
jest.mock('src/components/MessageToasts/withToasts', () => ({
  useToasts: () => ({ addDangerToast: jest.fn() }),
}));
jest.mock('./hooks/useAgentsCRUD', () => ({
  useAgentsCRUD: () => ({
    agents: [
      {
        id: 'agent-1',
        name: 'Ollama local',
        provider: 'ollama',
        model: 'qwen3:1.7b',
        is_active: true,
        is_default: true,
      },
    ],
    createAgent: jest.fn(),
    deleteAgent: jest.fn(),
    error: undefined,
    isLoading: false,
    testConnection: jest.fn(),
    updateAgent: mockUpdateAgent,
  }),
}));
jest.mock('./hooks/useGlobalAISettings', () => ({
  useGlobalAISettings: () => ({
    isLoading: false,
    settings: undefined,
    save: jest.fn(),
  }),
}));
jest.mock('./components/AgentsList', () => ({
  AgentsList: ({ agents, onSetDefault, onToggleActive }: AgentsListProps) => (
    <>
      <span>{agents[0].name}</span>
      <button type="button" onClick={() => onSetDefault(agents[0])}>
        Set default
      </button>
      <button type="button" onClick={() => onToggleActive(agents[0])}>
        Toggle agent
      </button>
    </>
  ),
}));
jest.mock('./components/AgentModal', () => ({ AgentModal: () => null }));
jest.mock('./components/GlobalSettings', () => ({
  GlobalSettings: () => null,
}));

test('lists configured agents and updates their active state', async () => {
  jest
    .spyOn(SupersetClient, 'get')
    .mockResolvedValue({ json: { result: [] } } as never);
  render(<AIAgentsSettings />);

  expect(screen.getByText('Ollama local')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Toggle agent' }));

  await waitFor(() =>
    expect(mockUpdateAgent).toHaveBeenCalledWith('agent-1', {
      is_active: false,
    }),
  );
});

test('sets an agent as default', async () => {
  jest
    .spyOn(SupersetClient, 'get')
    .mockResolvedValue({ json: { result: [] } } as never);
  render(<AIAgentsSettings />);

  fireEvent.click(screen.getByRole('button', { name: 'Set default' }));

  await waitFor(() =>
    expect(mockUpdateAgent).toHaveBeenCalledWith('agent-1', {
      is_default: true,
    }),
  );
});
