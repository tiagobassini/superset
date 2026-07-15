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
import { useMemo } from 'react';
import { t } from '@apache-superset/core/translation';
import { Button, Switch } from '@superset-ui/core/components';
import { ListView, type ListViewFetchDataConfig } from 'src/components';
import type { AIAgentConfiguration } from '../types';

const PAGE_SIZE = 25;

export interface AgentsListProps {
  agents: AIAgentConfiguration[];
  isLoading: boolean;
  onAdd: () => void;
  onDelete: (agent: AIAgentConfiguration) => void;
  onEdit: (agent: AIAgentConfiguration) => void;
  onToggleActive: (agent: AIAgentConfiguration) => void;
  refresh: () => Promise<void>;
}

/** Table of configured AI agents with status and management actions. */
export const AgentsList = ({
  agents,
  isLoading,
  onAdd,
  onDelete,
  onEdit,
  onToggleActive,
  refresh,
}: AgentsListProps) => {
  const columns = useMemo(
    () => [
      { Header: t('Name'), accessor: 'name' },
      { Header: t('Provider'), accessor: 'provider' },
      { Header: t('Model'), accessor: 'model' },
      {
        Cell: ({
          row: { original },
        }: {
          row: { original: AIAgentConfiguration };
        }) => (
          <Switch
            aria-label={t('Toggle status for %s', original.name)}
            checked={original.is_active}
            onChange={() => onToggleActive(original)}
          />
        ),
        Header: t('Status'),
        id: 'status',
      },
      {
        Cell: ({
          row: { original },
        }: {
          row: { original: AIAgentConfiguration };
        }) => (
          <>
            <Button
              buttonSize="small"
              buttonStyle="tertiary"
              onClick={() => onEdit(original)}
            >
              {t('Edit')}
            </Button>
            <Button
              buttonSize="small"
              buttonStyle="tertiary"
              onClick={() => onDelete(original)}
            >
              {t('Delete')}
            </Button>
          </>
        ),
        Header: t('Actions'),
        id: 'actions',
      },
    ],
    [onDelete, onEdit, onToggleActive],
  );

  const fetchData = async (config: ListViewFetchDataConfig) => {
    void config;
    return refresh();
  };

  return (
    <>
      <Button onClick={onAdd}>{t('Add Agent')}</Button>
      <ListView<AIAgentConfiguration>
        addDangerToast={() => undefined}
        addSuccessToast={() => undefined}
        columns={columns}
        count={agents.length}
        data={agents}
        emptyState={{ title: t('No AI agents have been configured') }}
        fetchData={fetchData}
        initialSort={[{ id: 'name', desc: false }]}
        loading={isLoading}
        pageSize={PAGE_SIZE}
        refreshData={refresh}
      />
    </>
  );
};
