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

export const AI_CHAT_PANEL_WIDTH = 380;
export const AI_CHAT_MOBILE_BREAKPOINT = 900;

// eslint-disable-next-line storybook/prefer-pascal-case
export const getAIChatLayoutState = (isOpen: boolean) => ({
  desktopPaddingRight: isOpen ? `${AI_CHAT_PANEL_WIDTH}px` : '0',
  hideContentOnMobile: isOpen,
});
