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
import { Fragment } from 'react';
import { styled } from '@apache-superset/core/theme';
import { Button } from '@superset-ui/core/components';
import type { PendingAction } from '../store/types';

const Card = styled.section`
  background: ${({ theme }) => theme.colorFillQuaternary};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: ${({ theme }) => theme.borderRadius}px;
  margin-top: ${({ theme }) => theme.sizeUnit * 2}px;
  padding: ${({ theme }) => theme.sizeUnit * 2}px;
`;

const Parameters = styled.dl`
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: ${({ theme }) => theme.sizeUnit}px ${({ theme }) => theme.sizeUnit * 2}px;
  margin: ${({ theme }) => theme.sizeUnit * 2}px 0;

  dt {
    font-weight: ${({ theme }) => theme.fontWeightStrong};
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
`;

const Actions = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
`;

const PlanDetails = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  margin: ${({ theme }) => theme.sizeUnit * 2}px 0;

  p,
  ul {
    margin: 0;
  }

  ul {
    padding-left: ${({ theme }) => theme.sizeUnit * 5}px;
  }

  li + li {
    margin-top: ${({ theme }) => theme.sizeUnit}px;
  }
`;

const PlanSection = styled.section`
  h4 {
    font-size: ${({ theme }) => theme.fontSizeSM}px;
    margin: 0 0 ${({ theme }) => theme.sizeUnit}px;
  }
`;

const formatParameter = (value: unknown) => {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const getResultUrl = (result: unknown) => {
  if (!result || typeof result !== 'object') return undefined;
  const candidate = (result as Record<string, unknown>).url;
  return typeof candidate === 'string' ? candidate : undefined;
};

const getRecord = (value: unknown) =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

const getString = (
  record: Record<string, unknown>,
  key: string,
): string | undefined => {
  const value = record[key];
  return typeof value === 'string' ? value : undefined;
};

const getList = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : [];

const formatListItem = (value: unknown) =>
  typeof value === 'string' ? value : formatParameter(value);

const chartTypeLabels: Record<string, string> = {
  echarts_timeseries_bar: 'barras temporais',
  echarts_timeseries_line: 'linha temporal',
  echarts_timeseries: 'série temporal',
  table: 'tabela',
  big_number: 'número destacado',
  pie: 'pizza',
};

const toolLabels: Record<string, string> = {
  create_chart: 'Criar gráfico',
  create_dataset: 'Criar dataset',
  create_dashboard: 'Criar dashboard',
  add_chart_to_dashboard: 'Publicar gráfico em dashboard',
  save_query: 'Salvar consulta',
};

const actionLabel = (value: unknown) => {
  const action = getRecord(value);
  const toolName = getString(action, 'tool_name');
  const params = getRecord(action.params);
  const chartSpec = getRecord(params.chart_spec);
  const title =
    getString(chartSpec, 'chart_title') ??
    getString(params, 'table_name') ??
    getString(params, 'dashboard_title') ??
    getString(params, 'label');

  return [
    toolName ? (toolLabels[toolName] ?? toolName) : 'Executar etapa',
    title,
  ]
    .filter(Boolean)
    .join(': ');
};

const PlanList = ({ items }: { items: unknown[] }) =>
  items.length > 0 ? (
    <ul>
      {items.map((item, index) => (
        <li key={`${formatListItem(item)}-${index}`}>{formatListItem(item)}</li>
      ))}
    </ul>
  ) : null;

const ExecutionPlanDetails = ({ action }: { action: PendingAction }) => {
  const source = getRecord(action.params.source);
  const chartSpec = getRecord(action.params.chart_specification);
  const vizType = getString(chartSpec, 'viz_type');
  const groupBy = getList(chartSpec.group_by).map(formatListItem);
  const metric = getString(chartSpec, 'metric');
  const timeColumn = getString(chartSpec, 'time_column');
  const chartTitle = getString(chartSpec, 'chart_title');
  const sourceName = getString(source, 'name');
  const database = getString(source, 'database');
  const schema = getString(source, 'schema');
  const sourceLocation = [database, schema].filter(Boolean).join(' / ');
  const effects = getList(action.params.effects);
  const findings = getList(action.params.findings);
  const readSteps = getList(action.params.read_steps);
  const actions = getList(action.params.actions);

  return (
    <PlanDetails>
      <PlanSection>
        <h4>Resumo</h4>
        <p>
          {chartTitle
            ? `Criar ou atualizar o gráfico "${chartTitle}".`
            : 'Executar o plano aprovado.'}
        </p>
      </PlanSection>
      {sourceName && (
        <PlanSection>
          <h4>Fonte de dados</h4>
          <p>
            {sourceName}
            {sourceLocation ? ` (${sourceLocation})` : ''}
          </p>
        </PlanSection>
      )}
      {(vizType || metric || timeColumn || groupBy.length > 0) && (
        <PlanSection>
          <h4>Configuração do gráfico</h4>
          <ul>
            {vizType && (
              <li>Visualização: {chartTypeLabels[vizType] ?? vizType}</li>
            )}
            {metric && <li>Métrica: {metric}</li>}
            {timeColumn && <li>Coluna temporal: {timeColumn}</li>}
            {groupBy.length > 0 && <li>Agrupamento: {groupBy.join(', ')}</li>}
          </ul>
        </PlanSection>
      )}
      {effects.length > 0 && (
        <PlanSection>
          <h4>O que será feito</h4>
          <PlanList items={effects} />
        </PlanSection>
      )}
      {findings.length > 0 && (
        <PlanSection>
          <h4>Validações realizadas</h4>
          <PlanList items={findings} />
        </PlanSection>
      )}
      {readSteps.length > 0 && (
        <PlanSection>
          <h4>Leituras usadas para planejar</h4>
          <PlanList items={readSteps} />
        </PlanSection>
      )}
      {actions.length > 0 && (
        <PlanSection>
          <h4>Etapas técnicas</h4>
          <PlanList items={actions.map(actionLabel)} />
        </PlanSection>
      )}
    </PlanDetails>
  );
};

export interface ActionConfirmationProps {
  action: PendingAction;
  onConfirm: (actionId: string) => void;
  onCancel: (actionId: string) => void;
}

/** Displays a pending AI action and requires an explicit user decision. */
export const ActionConfirmation = ({
  action,
  onConfirm,
  onCancel,
}: ActionConfirmationProps) => {
  const resultUrl = getResultUrl(action.result);

  return (
    <Card aria-label={`Ação da IA: ${action.type}`}>
      <strong>{action.description}</strong>
      {action.type === 'execution_plan' ? (
        <ExecutionPlanDetails action={action} />
      ) : Object.keys(action.params).length > 0 ? (
        <Parameters>
          {Object.entries(action.params).map(([name, value]) => (
            <Fragment key={name}>
              <dt>{name}</dt>
              <dd>{formatParameter(value)}</dd>
            </Fragment>
          ))}
        </Parameters>
      ) : null}
      {action.status === 'pending' && (
        <Actions>
          <Button buttonSize="small" onClick={() => onConfirm(action.id)}>
            Confirmar
          </Button>
          <Button
            buttonSize="small"
            buttonStyle="tertiary"
            onClick={() => onCancel(action.id)}
          >
            Cancelar
          </Button>
        </Actions>
      )}
      {action.status === 'confirmed' && <span>Executando ação…</span>}
      {action.status === 'cancelled' && <span>Ação cancelada.</span>}
      {action.status === 'failed' && (
        <span>
          Não foi possível executar a ação.
          {action.error ? ` ${action.error}` : ''}
        </span>
      )}
      {action.status === 'executed' && (
        <span>
          Ação concluída.{resultUrl && <a href={resultUrl}> Abrir recurso</a>}
        </span>
      )}
    </Card>
  );
};
