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
