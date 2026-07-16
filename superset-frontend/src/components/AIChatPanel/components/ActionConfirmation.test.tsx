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
import { fireEvent, render, screen } from 'spec/helpers/testing-library';
import { ActionConfirmation } from './ActionConfirmation';

test('shows action parameters and dispatches an explicit confirmation', () => {
  const onConfirm = jest.fn();
  render(
    <ActionConfirmation
      action={{
        id: 'action-id',
        type: 'create_dataset',
        description: 'Criar dataset',
        params: { table_name: 'sales' },
        status: 'pending',
      }}
      onCancel={jest.fn()}
      onConfirm={onConfirm}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));

  expect(screen.getByText('sales')).toBeInTheDocument();
  expect(onConfirm).toHaveBeenCalledWith('action-id');
});

test('renders execution plans as human-readable sections', () => {
  render(
    <ActionConfirmation
      action={{
        id: 'plan-id',
        type: 'execution_plan',
        description: 'Revisar e confirmar plano de execução',
        params: {
          chart_specification: {
            chart_title: 'Vendas por ano',
            metric: 'SUM(na_sales)',
            time_column: 'year',
            group_by: [],
            viz_type: 'echarts_timeseries_bar',
          },
          source: {
            name: 'video_game_sales',
            database: 'examples',
            schema: 'main',
          },
          effects: ['criar o gráfico de barras `Vendas por ano`'],
          findings: ['coluna temporal verificada: `year`'],
          read_steps: ['validar o schema do dataset selecionado'],
          actions: [
            {
              tool_name: 'create_chart',
              params: { chart_spec: { chart_title: 'Vendas por ano' } },
            },
          ],
        },
        status: 'pending',
      }}
      onCancel={jest.fn()}
      onConfirm={jest.fn()}
    />,
  );

  expect(screen.getByText('Resumo')).toBeInTheDocument();
  expect(screen.getByText(/video_game_sales/)).toBeInTheDocument();
  expect(
    screen.getByText('Visualização: barras temporais'),
  ).toBeInTheDocument();
  expect(screen.getByText('Métrica: SUM(na_sales)')).toBeInTheDocument();
  expect(screen.getByText('O que será feito')).toBeInTheDocument();
  expect(screen.queryByText('chart_specification')).not.toBeInTheDocument();
  expect(screen.queryByText('actions')).not.toBeInTheDocument();
});

test('shows the safe backend error when confirmed execution fails', () => {
  render(
    <ActionConfirmation
      action={{
        id: 'action-id',
        type: 'create_dataset',
        description: 'Criar dataset',
        params: {},
        status: 'failed',
        error: 'Dataset parameters are invalid.',
      }}
      onCancel={jest.fn()}
      onConfirm={jest.fn()}
    />,
  );

  expect(
    screen.getByText(/Dataset parameters are invalid/),
  ).toBeInTheDocument();
});
