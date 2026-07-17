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
import { useSelector } from 'react-redux';
import { useLocation } from 'react-router-dom';
import type { QueryEditor } from 'src/SqlLab/types';
import { DASHBOARD_HEADER_ID } from 'src/dashboard/util/constants';
import { applicationRoot } from 'src/utils/getBootstrapData';
import type { RootState } from 'src/views/store';
import type { PageContext } from '../store/types';

type ContextData = {
  dashboard?: { id?: number; title?: string; dashboard_title?: string };
  explore?: {
    chartId?: number;
    datasourceId?: number | string;
    vizType?: string;
  };
  sqlLab?: { databaseId?: number; sql?: string };
};

const getNumericQueryParam = (
  parameters: URLSearchParams,
  name: string,
): number | undefined => {
  const value = parameters.get(name);
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const normalizePathname = (pathname: string, appRoot = ''): string => {
  const root = appRoot.replace(/\/$/, '');
  if (root && pathname === root) return '/';
  if (root && pathname.startsWith(`${root}/`)) {
    return pathname.slice(root.length) || '/';
  }
  return pathname;
};

export const getAIPageContext = (
  pathname: string,
  search: string,
  data: ContextData,
  appRoot = '',
): PageContext => {
  const normalizedPathname = normalizePathname(pathname, appRoot);
  const parameters = new URLSearchParams(search);

  if (
    normalizedPathname.startsWith('/dashboard/') ||
    normalizedPathname.startsWith('/superset/dashboard/')
  ) {
    const title = data.dashboard?.dashboard_title ?? data.dashboard?.title;
    return {
      page: 'dashboard',
      resource_id: data.dashboard?.id,
      resource_name: title,
      metadata: {
        dashboard_id: data.dashboard?.id,
        dashboard_title: title,
      },
    };
  }

  if (normalizedPathname.startsWith('/explore')) {
    const chartId =
      data.explore?.chartId ?? getNumericQueryParam(parameters, 'slice_id');
    return {
      page: 'explore',
      resource_id: chartId,
      metadata: {
        chart_id: chartId,
        datasource_id: data.explore?.datasourceId,
        viz_type: data.explore?.vizType,
      },
    };
  }

  if (
    normalizedPathname.startsWith('/superset/sqllab') ||
    normalizedPathname.startsWith('/sqllab')
  ) {
    return {
      page: 'sqllab',
      metadata: {
        database_id: data.sqlLab?.databaseId,
        sql: data.sqlLab?.sql,
      },
    };
  }

  if (
    normalizedPathname.startsWith('/tablemodelview/') ||
    normalizedPathname.startsWith('/dataset/')
  ) {
    return { page: 'datasets' };
  }

  if (
    normalizedPathname.startsWith('/chart/') ||
    normalizedPathname.startsWith('/slice/')
  ) {
    return { page: 'charts' };
  }

  return { page: 'other' };
};

export const getActiveQueryEditor = (
  queryEditors: QueryEditor[],
  tabHistory: string[],
): QueryEditor | undefined => {
  const activeTabId = tabHistory[tabHistory.length - 1];
  return queryEditors.find(
    editor => (editor.tabViewId ?? editor.id) === activeTabId,
  );
};

/** Returns the AI-safe context for the page that is open in the SPA. */
export const useAIContext = (): PageContext => {
  const { pathname, search } = useLocation();
  const contextData = useSelector<RootState, ContextData>(state => {
    const dashboard: ContextData['dashboard'] = {
      id: state.dashboardInfo.id,
      title: state.dashboardLayout.present[DASHBOARD_HEADER_ID]?.meta.text,
    };
    const exploreState = state.explore;
    const formData = exploreState.form_data as unknown as {
      datasource_id?: number | string;
      viz_type?: string;
    };
    const slice = exploreState.slice as unknown as { id?: number } | null;
    const activeEditor = getActiveQueryEditor(
      state.sqlLab.queryEditors as QueryEditor[],
      state.sqlLab.tabHistory as string[],
    );

    return {
      dashboard,
      explore: {
        chartId: slice?.id,
        datasourceId: formData.datasource_id,
        vizType: formData.viz_type,
      },
      sqlLab: activeEditor
        ? { databaseId: activeEditor.dbId, sql: activeEditor.sql }
        : undefined,
    };
  });

  return useMemo(
    () => getAIPageContext(pathname, search, contextData, applicationRoot()),
    [contextData, pathname, search],
  );
};
