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

// TODO (Fase 2.3): implement useAgents hook
// Loads available AI agents from GET /api/v1/ai/agents.
// See docs/ai-integration/frontend-chat-sidebar.md for full specification.
import { SupersetClient } from '@superset-ui/core';
import { useCallback, useEffect, useState } from 'react';
import type { AIAgent } from '../store/types';

type AgentsResponse = { result?: Array<Record<string, unknown>> };
let cachedAgents: AIAgent[] | undefined;
let pendingRequest: Promise<AIAgent[]> | undefined;

const asAgent = (agent: Record<string, unknown>): AIAgent => ({
  id: String(agent.id),
  name: String(agent.name),
  model: String(agent.model),
  provider: agent.provider as AIAgent['provider'],
  isDefault: Boolean(agent.is_default),
  isActive: Boolean(agent.is_active),
});

export const fetchAIAgents = async (refresh = false): Promise<AIAgent[]> => {
  if (!refresh && cachedAgents) return cachedAgents;
  if (!refresh && pendingRequest) return pendingRequest;
  pendingRequest = SupersetClient.get({ endpoint: '/api/v1/ai/agents' })
    .then(({ json }) => ((json as AgentsResponse).result ?? []).map(asAgent))
    .then(agents => {
      cachedAgents = agents;
      return agents;
    })
    .finally(() => {
      pendingRequest = undefined;
    });
  return pendingRequest;
};

export const useAgents = () => {
  const [agents, setAgents] = useState<AIAgent[]>(cachedAgents ?? []);
  const [isLoading, setLoading] = useState(!cachedAgents);
  const [error, setError] = useState<Error | undefined>();
  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      setAgents(await fetchAIAgents(refresh));
      setError(undefined);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason
          : new Error('Unable to load AI agents'),
      );
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return { agents, isLoading, error, refresh: () => load(true) };
};
