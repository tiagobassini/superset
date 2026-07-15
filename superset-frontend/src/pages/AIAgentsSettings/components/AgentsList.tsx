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
import {
  Button,
  Switch,
  Table,
  type ColumnsType,
} from '@superset-ui/core/components';
import type { AIAgentConfiguration } from '../types';

const PAGE_SIZE = 25;

export interface AgentsListProps {
  agents: AIAgentConfiguration[];
  isLoading: boolean;
  onAdd: () => void;
  onDelete: (agent: AIAgentConfiguration) => void;
  onEdit: (agent: AIAgentConfiguration) => void;
  onToggleActive: (agent: AIAgentConfiguration) => void;
}

/** Table of configured AI agents with status and management actions. */
export const AgentsList = ({
  agents,
  isLoading,
  onAdd,
  onDelete,
  onEdit,
  onToggleActive,
}: AgentsListProps) => {
  const columns = useMemo<ColumnsType<AIAgentConfiguration>>(
    () => [
      { dataIndex: 'name', key: 'name', title: t('Name') },
      { dataIndex: 'provider', key: 'provider', title: t('Provider') },
      { dataIndex: 'model', key: 'model', title: t('Model') },
      {
        key: 'status',
        render: (_value, agent) => (
          <Switch
            aria-label={t('Toggle status for %s', agent.name)}
            checked={agent.is_active}
            onChange={() => onToggleActive(agent)}
          />
        ),
        title: t('Status'),
      },
      {
        key: 'actions',
        render: (_value, agent) => (
          <>
            <Button
              buttonSize="small"
              buttonStyle="tertiary"
              onClick={() => onEdit(agent)}
            >
              {t('Edit')}
            </Button>
            <Button
              buttonSize="small"
              buttonStyle="tertiary"
              onClick={() => onDelete(agent)}
            >
              {t('Delete')}
            </Button>
          </>
        ),
        title: t('Actions'),
      },
    ],
    [onDelete, onEdit, onToggleActive],
  );

  return (
    <>
      <Button onClick={onAdd}>{t('Add Agent')}</Button>
      <Table<AIAgentConfiguration>
        columns={columns}
        data={agents}
        loading={isLoading}
        locale={{ emptyText: t('No AI agents have been configured') }}
        defaultPageSize={PAGE_SIZE}
        rowKey="id"
        usePagination={agents.length > PAGE_SIZE}
      />
    </>
  );
};
