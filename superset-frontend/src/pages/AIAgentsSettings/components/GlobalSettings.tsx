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
import { useEffect } from 'react';
import { t } from '@apache-superset/core/translation';
import {
  Button,
  Checkbox,
  Form,
  InputNumber,
  Radio,
  Select,
} from '@superset-ui/core/components';
import type { AIGlobalSettings } from '../types';

type Role = { id: number; name: string };

export interface GlobalSettingsProps {
  isLoading: boolean;
  onSave: (settings: AIGlobalSettings) => Promise<void>;
  roles: Role[];
  settings?: AIGlobalSettings;
}

/** Form for the global safeguards and context options shared by all agents. */
export const GlobalSettings = ({
  isLoading,
  onSave,
  roles,
  settings,
}: GlobalSettingsProps) => {
  const [form] = Form.useForm<AIGlobalSettings>();

  useEffect(() => {
    if (settings) form.setFieldsValue(settings);
  }, [form, settings]);

  return (
    <section>
      <h3>{t('Global AI settings')}</h3>
      <Form form={form} layout="vertical" onFinish={onSave}>
        <Form.Item
          name="sql_confirmation_mode"
          label={t('SQL execution')}
          rules={[{ required: true }]}
        >
          <Radio.Group>
            <Radio value="always">
              {t('Always require user confirmation')}
            </Radio>
            <Radio value="roles_only">
              {t('Allow automatic execution for selected roles')}
            </Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item
          name="sql_confirmation_role_ids"
          label={t('Roles allowed to execute SQL automatically')}
        >
          <Select
            mode="multiple"
            options={roles.map(role => ({ label: role.name, value: role.id }))}
          />
        </Form.Item>
        <Form.Item
          name="max_query_rows"
          label={t('Maximum query rows')}
          rules={[{ required: true }]}
        >
          <InputNumber min={1} max={100000} />
        </Form.Item>
        <Form.Item
          name="history_storage"
          label={t('Conversation history storage')}
          rules={[{ required: true }]}
        >
          <Radio.Group>
            <Radio value="session">{t('Browser session')}</Radio>
            <Radio value="database">{t('Database')}</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item
          name="history_retention_days"
          label={t('History retention (days)')}
          rules={[{ required: true }]}
        >
          <InputNumber min={1} max={3650} />
        </Form.Item>
        <Form.Item label={t('Context sent to the model')}>
          <Form.Item name="send_page_context" valuePropName="checked" noStyle>
            <Checkbox>{t('Send current page automatically')}</Checkbox>
          </Form.Item>
          <Form.Item
            name="include_datasets_in_prompt"
            valuePropName="checked"
            noStyle
          >
            <Checkbox>{t('Include available datasets')}</Checkbox>
          </Form.Item>
          <Form.Item
            name="include_schema_in_prompt"
            valuePropName="checked"
            noStyle
          >
            <Checkbox>{t('Include dataset column schemas')}</Checkbox>
          </Form.Item>
        </Form.Item>
        <Button loading={isLoading} onClick={() => form.submit()}>
          {t('Save settings')}
        </Button>
      </Form>
    </section>
  );
};
