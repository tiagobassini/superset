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
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { fireEvent, render, screen } from 'spec/helpers/testing-library';
import AIChatPanel from './AIChatPanel';
import reducer, { initialAIChatState } from './store/aiChatSlice';

jest.mock('./hooks/useAgents', () => ({
  useAgents: () => ({ agents: [] }),
}));

jest.mock('./hooks/useAIChat', () => ({
  useAIChat: () => ({
    messages: [],
    isLoading: false,
    sendMessage: jest.fn(),
    confirmAction: jest.fn(),
    cancelAction: jest.fn(),
    clearChatHistory: jest.fn(),
  }),
}));

const renderPanel = (isOpen = false) => {
  const store = configureStore({
    reducer: { aiChat: reducer },
    preloadedState: { aiChat: { ...initialAIChatState, isOpen } },
  });

  render(
    <Provider store={store}>
      <AIChatPanel />
    </Provider>,
  );

  return store;
};

test('closes the open chat panel when Escape is pressed', () => {
  const store = renderPanel(true);

  fireEvent.keyDown(window, { key: 'Escape' });

  expect(store.getState().aiChat.isOpen).toBe(false);
  expect(
    screen.getByRole('button', { name: 'Abrir assistente de IA' }),
  ).toBeInTheDocument();
});

test('closes the panel when Escape is pressed from the message input', () => {
  const store = renderPanel(true);

  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Mensagem para IA' }), {
    key: 'Escape',
  });

  expect(store.getState().aiChat.isOpen).toBe(false);
});

test('focuses the message input after opening the panel', () => {
  renderPanel();

  fireEvent.click(
    screen.getByRole('button', { name: 'Abrir assistente de IA' }),
  );

  expect(
    screen.getByRole('textbox', { name: 'Mensagem para IA' }),
  ).toHaveFocus();
});
