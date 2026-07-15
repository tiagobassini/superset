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
import { useCallback, useEffect, useState } from 'react';
import type { AIAgentConfiguration, AIAgentUpdate } from '../types';

type AgentsResponse = {
  count: number;
  result: AIAgentConfiguration[];
};

const endpoint = '/api/v1/ai/agents?include_inactive=true';

/** Loads administrative agent data and provides mutations used by the settings page. */
// eslint-disable-next-line storybook/prefer-pascal-case
export const useAgentsCRUD = () => {
  const [agents, setAgents] = useState<AIAgentConfiguration[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | undefined>();

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const { json } = await SupersetClient.get({ endpoint });
      setAgents((json as AgentsResponse).result ?? []);
      setError(undefined);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason
          : new Error('Unable to load AI agents'),
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const updateAgent = useCallback(
    async (agentId: string, update: AIAgentUpdate) => {
      await SupersetClient.put({
        endpoint: `/api/v1/ai/agents/${agentId}`,
        jsonPayload: update,
      });
      await refresh();
    },
    [refresh],
  );

  const createAgent = useCallback(
    async (agent: AIAgentUpdate) => {
      await SupersetClient.post({
        endpoint: '/api/v1/ai/agents',
        jsonPayload: agent,
      });
      await refresh();
    },
    [refresh],
  );

  const deleteAgent = useCallback(
    async (agentId: string) => {
      await SupersetClient.delete({ endpoint: `/api/v1/ai/agents/${agentId}` });
      await refresh();
    },
    [refresh],
  );

  const testConnection = useCallback(async (agentId: string) => {
    const { json } = await SupersetClient.post({
      endpoint: `/api/v1/ai/agents/${agentId}/test`,
    });
    return Boolean((json as { success?: boolean }).success);
  }, []);

  return {
    agents,
    createAgent,
    deleteAgent,
    error,
    isLoading,
    refresh,
    testConnection,
    updateAgent,
  };
};
