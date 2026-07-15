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
import { styled } from '@apache-superset/core/theme';

const FloatingButton = styled.button`
  background: ${({ theme }) => theme.colorPrimary};
  border: 0;
  border-radius: 50%;
  bottom: ${({ theme }) => theme.sizeUnit * 4}px;
  box-shadow: ${({ theme }) => theme.boxShadowSecondary};
  color: ${({ theme }) => theme.colorWhite};
  cursor: pointer;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  height: 48px;
  position: fixed;
  right: ${({ theme }) => theme.sizeUnit * 4}px;
  width: 48px;
  z-index: 1001;
`;

export const ToggleButton = ({ onClick }: { onClick: () => void }) => (
  <FloatingButton
    type="button"
    onClick={onClick}
    aria-label="Abrir assistente de IA"
  >
    IA
  </FloatingButton>
);
