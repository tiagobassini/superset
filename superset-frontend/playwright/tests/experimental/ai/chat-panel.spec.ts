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
import { expect, test } from '@playwright/test';
import { AuthPage } from '../../../pages/AuthPage';
import { URL } from '../../../utils/urls';

const adminUsername = process.env.PLAYWRIGHT_ADMIN_USERNAME || 'admin';
const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD || 'general';

test('sends a message and displays the AI assistant response', async ({
  page,
}) => {
  await page.route('**/api/v1/ai/agents', route =>
    route.fulfill({ json: { result: [] } }),
  );
  await page.route('**/api/v1/ai/tasks', route =>
    route.fulfill({
      status: 202,
      json: {
        task_id: 'task-1',
        status: 'planning',
        events: [
          { sequence: 1, state: 'planning', message: 'Planejando a análise.' },
        ],
      },
    }),
  );
  await page.route('**/api/v1/ai/tasks/task-1?**', route =>
    route.fulfill({
      json: {
        task_id: 'task-1',
        status: 'completed',
        response: 'Resposta de teste',
        pending_actions: [],
        events: [
          { sequence: 2, state: 'completed', message: 'Análise concluída.' },
        ],
      },
    }),
  );
  const authPage = new AuthPage(page);
  await authPage.goto();
  await authPage.loginWithCredentials(adminUsername, adminPassword);
  await page.waitForURL(url => url.pathname.endsWith(URL.WELCOME));

  await page.getByRole('button', { name: 'Abrir assistente de IA' }).click();
  await page
    .getByRole('textbox', { name: 'Mensagem para IA' })
    .fill('Liste os dashboards');
  await page.getByRole('button', { name: 'Enviar mensagem' }).click();

  await expect(page.getByText('Resposta de teste')).toBeVisible();
});
