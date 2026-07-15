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
import { SupersetClient } from '@superset-ui/core';
import { t } from '@apache-superset/core/translation';
import {
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Select,
  Switch,
} from '@superset-ui/core/components';
import type { AIAgentConfiguration, AIAgentUpdate } from '../types';

type Role = {
  id: number;
  name: string;
};

type RolesResponse = {
  result?: Role[];
};

const TOOL_NAMES = [
  'list_databases',
  'list_database_tables',
  'get_table_schema',
  'list_datasets',
  'get_dataset_schema',
  'list_charts',
  'list_dashboards',
  'list_saved_queries',
  'get_saved_query',
  'run_sql_query',
  'save_sql_query',
  'create_chart',
  'edit_chart',
  'create_dashboard',
  'edit_dashboard',
  'add_chart_to_dashboard',
  'create_dataset',
];

type AgentForm = AIAgentUpdate & {
  name: string;
  model: string;
  provider: AIAgentConfiguration['provider'];
};

export interface AgentModalProps {
  agent?: AIAgentConfiguration;
  onCancel: () => void;
  onSave: (agent: AgentForm) => Promise<void>;
  onTestConnection: (agent: AIAgentConfiguration) => Promise<boolean>;
  open: boolean;
}

export const AgentModal = ({
  agent,
  onCancel,
  onSave,
  onTestConnection,
  open,
}: AgentModalProps) => {
  const [form] = Form.useForm<AgentForm>();
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<boolean | undefined>();
  const [roles, setRoles] = useState<Role[]>([]);

  useEffect(() => {
    let isMounted = true;
    const loadRoles = async () => {
      try {
        const { json } = await SupersetClient.get({
          endpoint: '/api/v1/security/roles/?q=(page:0,page_size:100)',
        });
        if (isMounted) setRoles((json as RolesResponse).result ?? []);
      } catch {
        if (isMounted) setRoles([]);
      }
    };
    void loadRoles();
    return () => {
      isMounted = false;
    };
  }, []);
  // The modal must replace stale form values whenever a different agent is selected.
  // eslint-disable-next-line react-you-might-not-need-an-effect/no-adjust-state-on-prop-change
  useEffect(() => {
    form.setFieldsValue({
      name: agent?.name ?? '',
      provider: agent?.provider ?? 'openai',
      model: agent?.model ?? '',
      response_language: agent?.response_language ?? 'pt-BR',
      base_url: agent?.base_url ?? undefined,
      role_ids: agent?.role_ids ?? [],
      is_active: agent?.is_active ?? true,
      is_default: agent?.is_default ?? false,
      enabled_tools: agent?.enabled_tools ?? TOOL_NAMES,
    });
    // eslint-disable-next-line react-you-might-not-need-an-effect/no-adjust-state-on-prop-change
    setTestResult(undefined);
  }, [agent, form, open]);
  return (
    <Modal
      show={open}
      title={agent ? t('Edit AI Agent') : t('Add AI Agent')}
      onHide={onCancel}
      footer={
        <>
          <Button buttonStyle="tertiary" onClick={onCancel}>
            {t('Cancel')}
          </Button>
          <Button loading={saving} onClick={() => form.submit()}>
            {t('Save')}
          </Button>
        </>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={async values => {
          setSaving(true);
          try {
            await onSave(values);
            onCancel();
          } finally {
            setSaving(false);
          }
        }}
      >
        <Form.Item
          name="name"
          label={t('Name')}
          rules={[{ required: true }, { max: 256 }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name="provider"
          label={t('Provider')}
          rules={[{ required: true }]}
        >
          <Select
            options={[
              { label: 'OpenAI', value: 'openai' },
              { label: 'Ollama', value: 'ollama' },
              { label: 'DeepSeek', value: 'deepseek' },
              { label: 'Anthropic', value: 'anthropic' },
              { label: 'Codex', value: 'codex' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="model"
          label={t('Model')}
          rules={[{ required: true }, { max: 128 }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name="response_language"
          label={t('Response language')}
          rules={[{ required: true }]}
        >
          <Select
            options={[
              { label: 'Português do Brasil', value: 'pt-BR' },
              { label: 'English', value: 'en-US' },
              { label: 'Español', value: 'es-ES' },
              { label: 'Français', value: 'fr-FR' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="api_key"
          label={t('API Key')}
          rules={[
            {
              validator: async (_, value) => {
                if (
                  !agent &&
                  form.getFieldValue('provider') !== 'ollama' &&
                  !value
                ) {
                  throw new Error(t('API key is required for cloud providers'));
                }
              },
            },
          ]}
        >
          <Input.Password
            placeholder={
              agent?.api_key_set
                ? t('Leave blank to keep the current key')
                : undefined
            }
          />
        </Form.Item>
        <Form.Item
          name="base_url"
          label={t('Base URL')}
          rules={[
            {
              validator: async (_, value) => {
                if (form.getFieldValue('provider') === 'ollama' && !value) {
                  throw new Error(t('Base URL is required for Ollama'));
                }
                if (!value) return;
                try {
                  const url = new URL(value);
                  if (
                    !['http:', 'https:'].includes(url.protocol) ||
                    !url.hostname
                  ) {
                    throw new Error();
                  }
                } catch {
                  throw new Error(t('Enter a valid HTTP(S) URL'));
                }
              },
            },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item name="is_default" valuePropName="checked">
          <Switch /> {t('Default agent')}
        </Form.Item>
        <Form.Item name="is_active" valuePropName="checked">
          <Switch /> {t('Active')}
        </Form.Item>
        <Form.Item
          name="role_ids"
          label={t('Roles allowed to use this agent')}
          extra={t('When empty, only administrators can use this agent.')}
        >
          <Select
            mode="multiple"
            options={roles.map(role => ({ label: role.name, value: role.id }))}
          />
        </Form.Item>
        <Form.Item name="enabled_tools" label={t('Enabled tools')}>
          <Checkbox.Group
            options={TOOL_NAMES.map(value => ({ label: value, value }))}
          />
        </Form.Item>
        {agent && (
          <>
            <Button
              buttonStyle="tertiary"
              onClick={async () => setTestResult(await onTestConnection(agent))}
            >
              {t('Test Connection')}
            </Button>
            {testResult !== undefined && (
              <span>
                {testResult
                  ? t('Connection successful')
                  : t('Connection failed')}
              </span>
            )}
          </>
        )}
      </Form>
    </Modal>
  );
};
