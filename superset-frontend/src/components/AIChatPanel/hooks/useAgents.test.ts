/** Licensed to the Apache Software Foundation (ASF) under one or more contributor license agreements. See the NOTICE file distributed with this work for additional information regarding copyright ownership. The ASF licenses this file to you under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0. Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License. */
import { SupersetClient } from '@superset-ui/core';
import { fetchAIAgents } from './useAgents';

test('loads and caches active AI agents', async () => {
  const get = jest.spyOn(SupersetClient, 'get').mockResolvedValue({ json: { result: [
    { id: 'id', name: 'Default', provider: 'openai', model: 'gpt', is_default: true, is_active: true },
  ] } } as never);
  await expect(fetchAIAgents(true)).resolves.toEqual([{
    id: 'id', name: 'Default', provider: 'openai', model: 'gpt', isDefault: true, isActive: true,
  }]);
  await fetchAIAgents();
  expect(get).toHaveBeenCalledTimes(1);
});
