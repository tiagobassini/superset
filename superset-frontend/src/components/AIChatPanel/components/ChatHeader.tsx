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
import { Button } from '@superset-ui/core/components';

const Header = styled.header`
  align-items: center;
  border-bottom: 1px solid ${({ theme }) => theme.colorBorder};
  display: flex;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  justify-content: space-between;
  padding: ${({ theme }) => theme.sizeUnit * 3}px;
`;

const Controls = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.sizeUnit}px;
`;

export interface ChatHeaderProps {
  onClose: () => void;
  onMinimize: () => void;
}

export const ChatHeader = ({ onClose, onMinimize }: ChatHeaderProps) => (
  <Header>
    Assistente de IA
    <Controls>
      <Button
        buttonSize="xsmall"
        buttonStyle="tertiary"
        onClick={onMinimize}
        aria-label="Minimizar assistente de IA"
      >
        −
      </Button>
      <Button
        buttonSize="xsmall"
        buttonStyle="tertiary"
        onClick={onClose}
        aria-label="Fechar assistente de IA"
      >
        ×
      </Button>
    </Controls>
  </Header>
);
