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
      {Object.keys(action.params).length > 0 && (
        <Parameters>
          {Object.entries(action.params).map(([name, value]) => (
            <Fragment key={name}>
              <dt>{name}</dt>
              <dd>{formatParameter(value)}</dd>
            </Fragment>
          ))}
        </Parameters>
      )}
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
