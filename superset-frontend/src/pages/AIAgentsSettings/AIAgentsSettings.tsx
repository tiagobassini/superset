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
import { useEffect, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { DeleteModal } from '@superset-ui/core/components';
import { SupersetClient } from '@superset-ui/core';
import SubMenu from 'src/features/home/SubMenu';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { AgentsList } from './components/AgentsList';
import { AgentModal } from './components/AgentModal';
import { GlobalSettings } from './components/GlobalSettings';
import { useAgentsCRUD } from './hooks/useAgentsCRUD';
import { useGlobalAISettings } from './hooks/useGlobalAISettings';
import type { AIAgentConfiguration } from './types';

type Role = { id: number; name: string };

/** Lists AI agents and exposes their management actions to administrators. */
const AIAgentsSettings = () => {
  const { addDangerToast } = useToasts();
  const {
    agents,
    createAgent,
    deleteAgent,
    error,
    isLoading,
    refresh,
    testConnection,
    updateAgent,
  } = useAgentsCRUD();
  const globalSettings = useGlobalAISettings();
  const [editingAgent, setEditingAgent] = useState<
    AIAgentConfiguration | undefined
  >();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<
    AIAgentConfiguration | undefined
  >();
  const [roles, setRoles] = useState<Role[]>([]);

  useEffect(() => {
    if (error) addDangerToast(error.message);
  }, [addDangerToast, error]);

  useEffect(() => {
    const loadRoles = async () => {
      try {
        const { json } = await SupersetClient.get({
          endpoint: '/api/v1/security/roles/?q=(page:0,page_size:100)',
        });
        setRoles((json as { result?: Role[] }).result ?? []);
      } catch {
        setRoles([]);
      }
    };
    void loadRoles();
  }, []);

  return (
    <>
      <SubMenu name={t('AI Agents')} />
      <AgentsList
        agents={agents}
        isLoading={isLoading}
        onAdd={() => {
          setEditingAgent(undefined);
          setIsModalOpen(true);
        }}
        onDelete={agent => {
          setAgentToDelete(agent);
        }}
        onEdit={agent => {
          setEditingAgent(agent);
          setIsModalOpen(true);
        }}
        onToggleActive={agent => {
          void updateAgent(agent.id, { is_active: !agent.is_active });
        }}
        refresh={refresh}
      />
      <AgentModal
        agent={editingAgent}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onSave={async values => {
          try {
            if (editingAgent) await updateAgent(editingAgent.id, values);
            else await createAgent(values);
          } catch (reason) {
            addDangerToast(String(reason));
            throw reason;
          }
        }}
        onTestConnection={agent => testConnection(agent.id)}
      />
      <GlobalSettings
        isLoading={globalSettings.isLoading}
        roles={roles}
        settings={globalSettings.settings}
        onSave={async settings => {
          try {
            await globalSettings.save(settings);
          } catch (reason) {
            addDangerToast(String(reason));
            throw reason;
          }
        }}
      />
      {agentToDelete && (
        <DeleteModal
          description={t('This action permanently deletes the AI agent.')}
          name={agentToDelete.name}
          open
          title={t('Delete AI agent?')}
          onConfirm={() => {
            void deleteAgent(agentToDelete.id).catch(reason =>
              addDangerToast(String(reason)),
            );
            setAgentToDelete(undefined);
          }}
          onHide={() => setAgentToDelete(undefined)}
        />
      )}
    </>
  );
};

export default AIAgentsSettings;
