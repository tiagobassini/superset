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
import {
  AI_CHAT_MOBILE_BREAKPOINT,
  AI_CHAT_PANEL_WIDTH,
  getAIChatLayoutState,
} from './layout';

test('reserves sidebar space on desktop and hides the main content on mobile', () => {
  expect(AI_CHAT_PANEL_WIDTH).toBe(380);
  expect(AI_CHAT_MOBILE_BREAKPOINT).toBe(900);
  expect(getAIChatLayoutState(true)).toEqual({
    desktopPaddingRight: '380px',
    hideContentOnMobile: true,
  });
  expect(getAIChatLayoutState(false)).toEqual({
    desktopPaddingRight: '0',
    hideContentOnMobile: false,
  });
});
