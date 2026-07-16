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
import { URL } from '../../../utils/urls';

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
  await page.goto(URL.WELCOME);

  await page.getByRole('button', { name: 'Abrir assistente de IA' }).click();
  await page
    .getByRole('textbox', { name: 'Mensagem para IA' })
    .fill('Liste os dashboards');
  await page.getByRole('button', { name: 'Enviar' }).click();

  await expect(page.getByText('Resposta de teste')).toBeVisible();
});

test('shows discovered alternatives and accepts a follow-up selection', async ({
  page,
}) => {
  let submittedTasks = 0;
  await page.route('**/api/v1/ai/agents', route =>
    route.fulfill({ json: { result: [] } }),
  );
  await page.route('**/api/v1/ai/tasks', route => {
    submittedTasks += 1;
    return route.fulfill({
      status: 202,
      json: {
        task_id: `task-${submittedTasks}`,
        status: 'planning',
        events: [],
      },
    });
  });
  await page.route('**/api/v1/ai/tasks/task-1?**', route =>
    route.fulfill({
      json: {
        task_id: 'task-1',
        status: 'awaiting_user_input',
        response:
          'Encontrei mais de uma fonte acessível relacionada a “vendas”:\n' +
          '1. Dataset `international_sales` — banco Examples; colunas: year, amount.\n' +
          '2. Dataset `sales_history` — banco Examples; colunas: year, amount.\n' +
          'Qual fonte deseja utilizar?',
        pending_actions: [],
        events: [],
      },
    }),
  );
  await page.route('**/api/v1/ai/tasks/task-2?**', route =>
    route.fulfill({
      json: {
        task_id: 'task-2',
        status: 'completed',
        response: 'Fonte sales_history selecionada; continuando o plano.',
        pending_actions: [],
        events: [],
      },
    }),
  );
  await page.goto(URL.WELCOME);

  await page.getByRole('button', { name: 'Abrir assistente de IA' }).click();
  const input = page.getByRole('textbox', { name: 'Mensagem para IA' });
  await input.fill('Crie um gráfico de vendas por ano');
  await page.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText('international_sales')).toBeVisible();
  await expect(page.getByText('sales_history')).toBeVisible();

  await input.fill('2');
  await page.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText('Fonte sales_history selecionada')).toBeVisible();
});
