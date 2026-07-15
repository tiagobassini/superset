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
import { Select } from '@superset-ui/core/components';
import type { AIAgent } from '../store/types';

const Container = styled.div`
  border-bottom: 1px solid ${({ theme }) => theme.colorBorder};
  padding: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export interface ModelSelectorProps {
  agents: AIAgent[];
  value: string | null;
  onChange: (id: string) => void;
}

/** Selects an active AI agent, or lets the backend resolve the default agent. */
export const ModelSelector = ({
  agents,
  value,
  onChange,
}: ModelSelectorProps) => {
  const activeAgents = agents.filter(agent => agent.isActive);
  const options = [
    { label: 'Agente padrão', value: '' },
    ...activeAgents.map(agent => ({
      label: `${agent.name} (${agent.model})`,
      value: agent.id,
    })),
  ];

  return (
    <Container>
      <Select
        ariaLabel="Agente de IA"
        onChange={selected => onChange(String(selected ?? ''))}
        options={options}
        placeholder="Agente padrão"
        value={value ?? ''}
      />
    </Container>
  );
};
