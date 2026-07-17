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
import { getActiveQueryEditor, getAIPageContext } from './useAIContext';

test('creates dashboard context from Redux data', () => {
  expect(
    getAIPageContext(
      '/dados/superset/dashboard/teste/',
      '',
      {
        dashboard: { id: 10, dashboard_title: 'Sales' },
      },
      '/dados',
    ),
  ).toMatchObject({
    page: 'dashboard',
    resource_id: 10,
    resource_name: 'Sales',
    metadata: { dashboard_id: 10, dashboard_title: 'Sales' },
  });
});

test('creates Explore and SQL Lab contexts', () => {
  expect(
    getAIPageContext(
      '/dados/explore/',
      '?slice_id=5',
      {
        explore: { datasourceId: 3, vizType: 'bar' },
      },
      '/dados',
    ),
  ).toMatchObject({
    page: 'explore',
    resource_id: 5,
    metadata: { chart_id: 5, datasource_id: 3, viz_type: 'bar' },
  });
  expect(
    getAIPageContext(
      '/dados/sqllab',
      '',
      {
        sqlLab: { databaseId: 4, sql: 'SELECT 1' },
      },
      '/dados',
    ),
  ).toMatchObject({
    page: 'sqllab',
    metadata: { database_id: 4, sql: 'SELECT 1' },
  });
});

test('creates list contexts for datasets and charts', () => {
  expect(
    getAIPageContext('/dados/tablemodelview/list/', '', {}, '/dados'),
  ).toEqual({ page: 'datasets' });
  expect(getAIPageContext('/dados/chart/list/', '', {}, '/dados')).toEqual({
    page: 'charts',
  });
});

test('uses other context outside AI-aware pages', () => {
  expect(getAIPageContext('/dados/security/list_roles/', '', {}, '/dados')).toEqual({
    page: 'other',
  });
});

test('uses the most recently selected SQL Lab tab', () => {
  const editors = [
    { id: 'first', tabViewId: 'first-tab' },
    { id: 'second', tabViewId: 'second-tab' },
  ];

  expect(
    getActiveQueryEditor(editors as never, ['first-tab', 'second-tab']),
  ).toMatchObject({ id: 'second' });
});
