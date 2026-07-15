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
import { SupersetClient } from '@superset-ui/core';
import { useCallback, useEffect, useState } from 'react';
import type { AIGlobalSettings } from '../types';

type SettingsResponse = { result: AIGlobalSettings };

/** Loads and saves global AI preferences for the settings administrator. */
// eslint-disable-next-line storybook/prefer-pascal-case
export const useGlobalAISettings = () => {
  const [settings, setSettings] = useState<AIGlobalSettings>();
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async (isMounted = () => true) => {
    setIsLoading(true);
    try {
      const { json } = await SupersetClient.get({
        endpoint: '/api/v1/ai/settings',
      });
      if (isMounted()) setSettings((json as SettingsResponse).result);
    } finally {
      if (isMounted()) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    void refresh(() => mounted);
    return () => {
      mounted = false;
    };
  }, [refresh]);

  const save = useCallback(async (values: AIGlobalSettings) => {
    const { json } = await SupersetClient.put({
      endpoint: '/api/v1/ai/settings',
      jsonPayload: values,
    });
    setSettings((json as SettingsResponse).result);
  }, []);

  return { isLoading, refresh, save, settings };
};
