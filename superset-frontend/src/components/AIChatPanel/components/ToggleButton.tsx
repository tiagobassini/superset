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
import { useRef } from 'react';
import { styled } from '@apache-superset/core/theme';

const BUTTON_SIZE = 48;
const MIN_TOP = 112;
const EDGE_GAP = 16;
const DRAG_THRESHOLD = 4;

const FloatingButton = styled.button<{ $top: number }>`
  background: ${({ theme }) => theme.colorPrimary};
  border: 0;
  border-radius: 50%;
  box-shadow: ${({ theme }) => theme.boxShadowSecondary};
  color: ${({ theme }) => theme.colorWhite};
  cursor: grab;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  height: ${BUTTON_SIZE}px;
  position: fixed;
  right: ${({ theme }) => theme.sizeUnit * 4}px;
  top: ${({ $top }) => $top}px;
  touch-action: none;
  width: ${BUTTON_SIZE}px;
  z-index: 1001;

  &:active {
    cursor: grabbing;
  }
`;

export const DEFAULT_TOGGLE_TOP = MIN_TOP;

export interface ToggleButtonProps {
  onClick: () => void;
  onTopChange: (top: number) => void;
  top: number;
}

/** Opens the chat panel and can be dragged vertically below the navigation. */
export const ToggleButton = ({
  onClick,
  onTopChange,
  top,
}: ToggleButtonProps) => {
  const dragStart = useRef<{ pointerY: number; top: number } | undefined>(
    undefined,
  );
  const hasDragged = useRef(false);

  const getBoundedTop = (nextTop: number) => {
    const maximumTop = Math.max(
      MIN_TOP,
      window.innerHeight - BUTTON_SIZE - EDGE_GAP,
    );
    return Math.min(Math.max(MIN_TOP, nextTop), maximumTop);
  };

  return (
    <FloatingButton
      $top={top}
      type="button"
      aria-label="Abrir assistente de IA"
      onClick={event => {
        if (hasDragged.current) {
          event.preventDefault();
          hasDragged.current = false;
          return;
        }
        onClick();
      }}
      onPointerDown={event => {
        if (event.button !== 0) return;
        dragStart.current = { pointerY: event.clientY, top };
        hasDragged.current = false;
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={event => {
        if (!dragStart.current) return;
        const distance = event.clientY - dragStart.current.pointerY;
        if (Math.abs(distance) >= DRAG_THRESHOLD) {
          hasDragged.current = true;
        }
        onTopChange(getBoundedTop(dragStart.current.top + distance));
      }}
      onPointerUp={event => {
        dragStart.current = undefined;
        event.currentTarget.releasePointerCapture?.(event.pointerId);
      }}
      onPointerCancel={() => {
        dragStart.current = undefined;
      }}
      title="Arraste verticalmente para reposicionar o assistente de IA"
    >
      IA
    </FloatingButton>
  );
};
