# Especificação Frontend — Barra Lateral de Chat (AIChatPanel)

## Visão Geral

O `AIChatPanel` é uma barra lateral retráctil posicionada à direita da interface do Superset. Ela está disponível em todas as páginas para usuários com permissão de uso da IA. O painel é inspirado nas extensões de IA do VS Code (GitHub Copilot Chat, Continue, etc.).

---

## Layout e Estrutura Visual

```
┌──────────────────────────────────┐
│  🤖 AI Assistant          [×][─] │  ← Header: título + botões fechar/minimizar
├──────────────────────────────────┤
│  Modelo: [GPT-4o          ▼]     │  ← Model selector
│  Agente: [Prod - OpenAI   ▼]     │  ← Agent selector (configurados no Settings)
├──────────────────────────────────┤
│                                  │
│  ┌──────────────────────────┐   │
│  │ 👤 Você                  │   │  ← Mensagem do usuário
│  │ Cria um bar chart de     │   │
│  │ vendas por região        │   │
│  └──────────────────────────┘   │
│                                  │
│  ┌──────────────────────────┐   │
│  │ 🤖 AI                    │   │  ← Resposta da IA
│  │ Encontrei o dataset      │   │
│  │ sales_data. Vou criar    │   │
│  │ um bar chart com:        │   │
│  │                          │   │
│  │ • Dataset: sales_data    │   │
│  │ • Tipo: Bar Chart        │   │
│  │ • X: region              │   │
│  │ • Y: total_sales         │   │
│  │                          │   │
│  │ [✅ Confirmar] [❌ Cancelar] │  ← Action confirmation inline
│  └──────────────────────────┘   │
│                                  │
│  [🔄 digitando...]               │  ← Loading indicator (streaming)
│                                  │
├──────────────────────────────────┤
│  📎 Contexto: Dashboard #5      │  ← Contexto atual (readonly)
├──────────────────────────────────┤
│  ┌──────────────────────────┐   │
│  │ Digite sua mensagem...   │   │  ← Textarea
│  └──────────────────────────┘   │
│  [🗑️ Limpar]          [Enviar →] │  ← Ações do input
└──────────────────────────────────┘
```

### Estados do Painel

- **Expandido**: largura fixa de `380px`, visível à direita do conteúdo principal
- **Recolhido**: apenas um botão flutuante circular `🤖` aparece no canto inferior direito
- **Transição**: animação suave `slide-in/slide-out` de `300ms`
- O layout principal do Superset deve se adaptar (margin-right) quando o painel está aberto, sem sobrepor o conteúdo

---

## Componentes React

### Estrutura de Arquivos

```
superset-frontend/src/components/AIChatPanel/
├── index.tsx                    # Ponto de entrada, exporta AIChatPanel
├── AIChatPanel.tsx              # Componente principal (container)
├── AIChatPanel.test.tsx         # Testes unitários
├── components/
│   ├── ChatHeader.tsx           # Header com título e controles
│   ├── ModelSelector.tsx        # Dropdown de seleção de modelo/agente
│   ├── MessageList.tsx          # Lista de mensagens com scroll
│   ├── MessageBubble.tsx        # Bolha individual de mensagem
│   ├── ActionConfirmation.tsx   # Card de confirmação de ação da IA
│   ├── ContextBadge.tsx         # Exibição do contexto atual
│   ├── ChatInput.tsx            # Textarea + botão enviar
│   └── ToggleButton.tsx         # Botão flutuante para abrir o painel
├── hooks/
│   ├── useAIChat.ts             # Lógica central do chat (envio, histórico)
│   ├── useAIContext.ts          # Captura o contexto da tela atual
│   └── useAgents.ts             # Carrega agentes disponíveis da API
├── store/
│   ├── aiChatSlice.ts           # Redux slice (ou Zustand store)
│   └── types.ts                 # TypeScript types e interfaces
└── utils/
    ├── sessionStorage.ts        # Persistência do histórico na sessão
    └── contextExtractors.ts     # Funções para extrair contexto por página
```

### Tipos TypeScript Principais

```typescript
// store/types.ts

export type MessageRole = 'user' | 'assistant' | 'system';

export type ActionStatus = 'pending' | 'confirmed' | 'cancelled' | 'executed' | 'failed';

export interface PendingAction {
  id: string;
  type: string;           // ex: 'create_chart', 'run_query'
  description: string;    // Texto legível para o usuário
  params: Record<string, unknown>;
  status: ActionStatus;
  result?: unknown;       // Resultado após execução
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  pendingActions?: PendingAction[];  // Ações que aguardam confirmação
  isStreaming?: boolean;
}

export interface AIAgent {
  id: string;
  name: string;
  provider: 'openai' | 'ollama' | 'deepseek' | 'anthropic' | 'codex';
  model: string;
  isDefault: boolean;
}

export interface PageContext {
  page: 'dashboard' | 'explore' | 'sqllab' | 'datasets' | 'charts' | 'other';
  resourceId?: number | string;
  resourceName?: string;
  metadata?: Record<string, unknown>;
}

export interface AIChatState {
  isOpen: boolean;
  messages: ChatMessage[];
  selectedAgentId: string | null;
  isLoading: boolean;
  currentContext: PageContext;
}
```

---

## Comportamento e UX

### Captura de Contexto

O hook `useAIContext` extrai automaticamente o contexto da página atual baseado na URL e no estado do Redux do Superset:

| Página           | Contexto capturado                                      |
|------------------|---------------------------------------------------------|
| Dashboard        | `dashboard_id`, `dashboard_title`, lista de charts      |
| Explore/Chart    | `chart_id`, `datasource_id`, `viz_type`, filtros ativos |
| SQL Lab          | `database_id`, SQL atual no editor, resultado visível   |
| Datasets         | Lista de datasets visíveis                              |
| Outras páginas   | Apenas `{ page: 'other' }`                              |

O contexto é enviado automaticamente em cada mensagem — o usuário não precisa informar manualmente.

### Fluxo de Envio de Mensagem

```
1. Usuário digita e clica em Enviar (ou pressiona Ctrl+Enter)
2. Mensagem é adicionada ao histórico local (sessionStorage)
3. Loading indicator aparece
4. POST /api/v1/ai/chat é chamado com { message, context, agent_id, history }
5. Resposta retorna:
   a. Texto da IA → exibido como MessageBubble
   b. pending_actions (opcional) → exibidos como ActionConfirmation cards
6. Se há ações pendentes, botões Confirmar/Cancelar ficam ativos
7. Usuário confirma → POST /api/v1/ai/confirm_action com { action_id }
8. Resultado da ação é exibido (sucesso/erro + link para o recurso criado)
```

### Confirmação de Ações

O componente `ActionConfirmation` exibe:
- Tipo da ação (ícone + texto)
- Resumo dos parâmetros em formato legível
- Preview quando possível (ex: SQL a ser executado)
- Botões: **Confirmar** (verde) e **Cancelar** (cinza)
- Estado de loading enquanto a ação é executada
- Resultado: link clicável para o recurso criado/editado

### Persistência do Histórico

```typescript
// utils/sessionStorage.ts

const STORAGE_KEY = 'superset_ai_chat_history';

export const saveHistory = (messages: ChatMessage[]): void => {
  // Limita a 100 mensagens para não explodir o sessionStorage
  const trimmed = messages.slice(-100);
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
};

export const loadHistory = (): ChatMessage[] => {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

export const clearHistory = (): void => {
  sessionStorage.removeItem(STORAGE_KEY);
};
```

**Preparação para persistência em banco**: o store deve ter uma action `syncHistoryToServer()` que pode ser implementada futuramente chamando `POST /api/v1/ai/history`.

---

## Integração no Layout do Superset

### Ponto de Injeção

O `AIChatPanel` deve ser injetado no componente de layout raiz do Superset. Modificação mínima no core:

```tsx
// superset-frontend/src/views/App.tsx (ou equivalente)
// Adicionar condicionalmente quando ENABLE_AI_INTEGRATION = true

import { AIChatPanel } from 'src/components/AIChatPanel';
import { isFeatureEnabled, FeatureFlag } from 'src/featureFlags';

// No JSX do layout:
{isFeatureEnabled(FeatureFlag.ENABLE_AI_INTEGRATION) && <AIChatPanel />}
```

O layout principal deve adicionar `padding-right: 380px` quando o painel estiver aberto, usando o estado global do Redux.

---

## Acessibilidade

- O painel deve ter `role="complementary"` e `aria-label="AI Assistant"`
- O botão flutuante deve ter `aria-label="Abrir assistente de IA"`
- Foco deve ser movido para o input de texto quando o painel abre
- Suporte a navegação por teclado: `Esc` fecha o painel, `Ctrl+Enter` envia mensagem
- Mensagens devem ter `aria-live="polite"` para leitores de tela

---

## Feature Flag

O painel inteiro é controlado pela feature flag `ENABLE_AI_INTEGRATION`. Quando desabilitada, nenhum código do painel é carregado (code splitting via lazy import).

```python
# superset/config.py (adição)
FEATURE_FLAGS: dict[str, bool] = {
    # ... flags existentes ...
    "ENABLE_AI_INTEGRATION": False,  # Desabilitado por padrão
}
```
