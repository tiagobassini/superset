# Tarefas de Desenvolvimento — AI Integration Plugin

> Referência: [overview.md](./overview.md) | [frontend-chat-sidebar.md](./frontend-chat-sidebar.md) | [backend-api-tools.md](./backend-api-tools.md) | [settings-agents-page.md](./settings-agents-page.md) | [security-permissions.md](./security-permissions.md)

---

## Fase 0 — Fundação (Pré-requisitos)

Tarefas de setup que desbloqueiam todas as demais.

### 0.1 Feature Flag e Configuração
- [x] Adicionar `ENABLE_AI_INTEGRATION: False` em `superset/config.py` (seção IN DEVELOPMENT, linha 576)
- [x] Adicionar a flag no enum `FeatureFlag` do frontend (`superset-frontend/packages/superset-ui-core/src/utils/featureFlags.ts`, em ordem alfabética: `EnableAiIntegration = 'ENABLE_AI_INTEGRATION'`)
- [x] Verificar que o mecanismo de feature flag cobre tanto backend quanto frontend
  - Backend: `is_feature_enabled("ENABLE_AI_INTEGRATION")`
  - Frontend: `isFeatureEnabled(FeatureFlag.EnableAiIntegration)`

### 0.2 Estrutura de Módulos
- [x] Criar módulo `superset/ai/` com `__init__.py`
- [x] Criar diretórios `superset/ai/providers/` e `superset/ai/tools/`
- [x] Criar estrutura de componentes no frontend: `superset-frontend/src/components/AIChatPanel/`
  - `index.tsx`, `AIChatPanel.tsx` (stub)
  - `store/types.ts` (tipos TypeScript completos), `store/aiChatSlice.ts`
  - `hooks/useAIChat.ts`, `hooks/useAIContext.ts`, `hooks/useAgents.ts`
  - `utils/sessionStorage.ts` (implementado)
  - `components/` — 7 stubs: ChatHeader, ModelSelector, MessageList, MessageBubble, ActionConfirmation, ContextBadge, ChatInput, ToggleButton
- [x] Criar estrutura de páginas: `superset-frontend/src/pages/AIAgentsSettings/`
  - `index.tsx`, `AIAgentsSettings.tsx` (stub)

### 0.3 Dependências
- [x] Adicionar ao `pyproject.toml` como optional extra `[ai]`:
  - `openai>=1.0.0, <2.0.0` — client OpenAI (também usado para DeepSeek/Codex via `base_url`)
  - `anthropic>=0.20.0, <1.0.0` — client Anthropic Claude
  - `httpx>=0.25.0, <1.0.0` — usado pelo adapter Ollama (API REST local, sem SDK dedicado)
  - Instalar com: `pip install apache-superset[ai]`
- [x] Documentar mecanismo de ativação via Docker (`docker/requirements-local.txt`)
  - Ver seção "Como Ativar e Desativar" em `docs/ai-integration/overview.md`
- [ ] Verificar se `httpx` já é transitiva de outro pacote após gerar o `requirements/base.txt`
  - Se sim, remover do extra `ai` (mas manter o comentário explicativo)
  - Para regenerar: `./scripts/uv-pip-compile.sh` (requer ambiente configurado)

---

## Fase 1 — Backend Core

### 1.1 Modelo de Dados e Migration
- [x] Criar `AIAgent` model em `superset/ai/models.py`
  - Campos: `id` (UUID), `name`, `provider`, `model`, `base_url`, `api_key_encrypted`, `is_default`, `is_active`, `changed_on`, `created_on`
- [x] Criar tabela de associação `ai_agent_roles` (many-to-many com `ab_role`)
- [x] Criar migration Alembic: `superset/migrations/versions/2026-07-14_18-22_33c72567c98a_add_ai_agent.py`
- [x] Testar migration up/down

### 1.2 Permissões
- [x] Registrar novas permissões no Flask-AppBuilder:
  - `can_use_ai_chat`
  - `can_manage_ai_agents`
  - `can_ai_run_sql`
  - `can_ai_create_charts` / `can_ai_edit_charts`
  - `can_ai_create_dashboards` / `can_ai_edit_dashboards`
  - `can_ai_create_datasets`
- [x] Adicionar permissões ao role `Admin` no `superset/security/manager.py`
- [x] Escrever testes de autorização para cada permissão

### 1.3 Adaptadores de Provedor
- [ ] Criar `AIProviderAdapter` (ABC) em `superset/ai/providers/base.py`
- [ ] Implementar `OpenAIProviderAdapter` (OpenAI + DeepSeek + Codex via `base_url`)
- [ ] Implementar `OllamaProviderAdapter` (API REST do Ollama)
- [ ] Implementar `AnthropicProviderAdapter`
- [ ] Método `test_connection()` em cada adapter
- [ ] Testes unitários para cada adapter (com mock das APIs externas)

### 1.4 Tool Registry
- [ ] Criar `AITool` base class em `superset/ai/tools/base.py`
- [ ] Criar `ToolRegistry` singleton em `superset/ai/tools/registry.py`
- [ ] Implementar tools de **consulta** (sem confirmação):
  - [ ] `ListDatabasesTool`
  - [ ] `ListDatabaseTablesTool` — lista tabelas de um banco via API de schema do Superset (mesmo endpoint usado pelo SQL Lab para autocomplete)
  - [ ] `GetTableSchemaTool` — retorna colunas/tipos de uma tabela do banco sem precisar de dataset configurado
  - [ ] `ListDatasetsTool`
  - [ ] `GetDatasetSchemaTool`
  - [ ] `ListChartsTool`
  - [ ] `ListDashboardsTool`
  - [ ] `ListSavedQueriesTool`
- [ ] Implementar tools de **escrita** (com confirmação):
  - [ ] `RunSQLQueryTool` — usa API do SQL Lab
  - [ ] `SaveSQLQueryTool`
  - [ ] `CreateChartTool`
  - [ ] `EditChartTool`
  - [ ] `CreateDashboardTool`
  - [ ] `EditDashboardTool`
  - [ ] `AddChartToDashboardTool`
  - [ ] `CreateDatasetTool`
- [ ] Testes unitários para cada tool (verificar autorização + execução)

### 1.5 AI Orchestrator
- [ ] Implementar `AIOrchestrator` em `superset/ai/orchestrator.py`
- [ ] Lógica de montagem do system prompt com contexto dinâmico
- [ ] Loop de tool calling (executar tools sem confirmação, acumular tools com confirmação)
- [ ] Cache de `PendingAction` com TTL de 10 min (usando cache do Superset)
- [ ] Método `confirm_and_execute(action_id)` para execução pós-confirmação
- [ ] Sanitização de strings externas antes de incluir no prompt
- [ ] Testes unitários com mocks do provedor

### 1.6 API REST
- [ ] Implementar `AIRestApi` em `superset/ai/api.py` (herdar de `BaseSupersetView`)
- [ ] `POST /api/v1/ai/chat` — com validação de schema via Marshmallow
- [ ] `POST /api/v1/ai/confirm_action`
- [ ] `GET /api/v1/ai/agents`
- [ ] `GET /api/v1/ai/agents/<id>` (admin)
- [ ] `POST /api/v1/ai/agents` (admin)
- [ ] `PUT /api/v1/ai/agents/<id>` (admin)
- [ ] `DELETE /api/v1/ai/agents/<id>` (admin)
- [ ] `POST /api/v1/ai/agents/<id>/test` (admin)
- [ ] Registrar `AIRestApi` no `superset/app.py` (condicionado à feature flag)
- [ ] Testes de integração para todos os endpoints

---

## Fase 2 — Frontend Core

### 2.1 Store / State Management
- [ ] Criar `aiChatSlice.ts` com estado: `isOpen`, `messages`, `selectedAgentId`, `isLoading`, `currentContext`
- [ ] Adicionar slice ao Redux store do Superset
- [ ] Criar `sessionStorage.ts` para persistência do histórico
- [ ] Definir todos os tipos TypeScript em `store/types.ts`

### 2.2 Hook de Contexto
- [ ] Implementar `useAIContext.ts` — extrai contexto da página atual via URL + Redux
  - Dashboard: `dashboard_id`, `dashboard_title`
  - Explore: `chart_id`, `datasource_id`, `viz_type`
  - SQL Lab: `database_id`, SQL atual
  - Demais: `{ page: 'other' }`

### 2.3 Hook de Agentes
- [ ] Implementar `useAgents.ts` — carrega lista de agentes de `GET /api/v1/ai/agents`
- [ ] Cache local dos agentes (evitar requests repetidos)

### 2.4 Hook Central do Chat
- [ ] Implementar `useAIChat.ts`:
  - `sendMessage(text)` → POST /api/v1/ai/chat
  - `confirmAction(actionId)` → POST /api/v1/ai/confirm_action
  - `cancelAction(actionId)`
  - Gerenciamento do histórico (sessionStorage)
  - Estado de loading por mensagem

### 2.5 Componentes do Chat
- [ ] `ToggleButton.tsx` — botão flutuante para abrir o painel
- [ ] `ChatHeader.tsx` — título + botões fechar/minimizar
- [ ] `ModelSelector.tsx` — dropdown de seleção de agente
- [ ] `MessageBubble.tsx` — bolha de mensagem (user/assistant)
- [ ] `ActionConfirmation.tsx` — card de confirmação com parâmetros + Confirmar/Cancelar
- [ ] `ContextBadge.tsx` — exibe contexto atual (readonly)
- [ ] `MessageList.tsx` — lista com scroll automático para última mensagem
- [ ] `ChatInput.tsx` — textarea + botão enviar (Ctrl+Enter support)
- [ ] `AIChatPanel.tsx` — componente principal que compõe todos os acima
- [ ] Testes unitários para componentes principais

### 2.6 Integração no Layout
- [ ] Identificar o componente raiz de layout do Superset
- [ ] Injetar `<AIChatPanel />` condicionado à feature flag
- [ ] Ajustar `padding-right` do layout quando painel estiver aberto
- [ ] Garantir que o painel não sobreponha conteúdo em nenhuma resolução

### 2.7 Acessibilidade
- [ ] `role="complementary"` e `aria-label` no painel
- [ ] `aria-live="polite"` na lista de mensagens
- [ ] `Esc` fecha o painel
- [ ] `Ctrl+Enter` envia mensagem
- [ ] Foco movido para o input ao abrir o painel

---

## Fase 3 — Settings Page

### 3.1 Página de Listagem de Agentes
- [ ] Criar `AIAgentsSettings.tsx` usando `ListView` do Superset
- [ ] Colunas: Nome, Provedor, Modelo, Status, Ações (editar/deletar)
- [ ] Botão "Add Agent"
- [ ] Toggle ativar/desativar sem deletar

### 3.2 Modal Criar/Editar Agente
- [ ] `AgentModal.tsx` com formulário completo
- [ ] Campos: Nome, Provedor, Modelo, API Key (mascarada), URL Base
- [ ] Seção de Roles com permissão
- [ ] Checkboxes de Tools habilitadas
- [ ] Botão "Testar Conexão" com feedback
- [ ] Validação de formulário (campo obrigatórios, URL válida)

### 3.3 Configurações Globais
- [ ] `GlobalSettings.tsx` com opções de comportamento
- [ ] Modo de confirmação de SQL (sempre / por role)
- [ ] Limite de linhas de query
- [ ] Storage do histórico (session / banco)
- [ ] Opções de contexto enviado ao modelo

### 3.4 Integração no Menu Settings
- [ ] Adicionar item "AI Agents" no menu Settings do Superset
- [ ] Visível apenas com `ENABLE_AI_INTEGRATION=true` e `can_manage_ai_agents`
- [ ] Rota `/settings/ai/agents` registrada no router

---

## Fase 4 — Qualidade e Observabilidade

### 4.1 Testes
- [ ] Cobertura de testes unitários ≥ 80% para `superset/ai/`
- [ ] Testes de integração para todos os endpoints de API
- [ ] Testes de componente React para `AIChatPanel` e `AIAgentsSettings`
- [ ] Testes E2E (Playwright) para fluxo completo:
  - Abrir painel, enviar mensagem, confirmar ação, ver resultado
  - Criar agente na página de settings, testar conexão

### 4.2 Auditoria e Logging
- [ ] Log de todas as ações de escrita executadas via IA
- [ ] Log de falhas de autorização (tentativas bloqueadas)
- [ ] Integrar com o `event_logger` existente do Superset

### 4.3 Documentação
- [ ] Docstrings em todas as classes e métodos públicos Python
- [ ] Comentários TSDoc nos hooks e componentes principais
- [ ] Atualizar `UPDATING.md` com a nova feature flag
- [ ] Guia de configuração rápida (primeiros passos para habilitar e configurar um agente)

---

## Fase 5 — Preparação para PR Upstream

### 5.1 Compatibilidade
- [ ] Verificar que todos os testes existentes do Superset ainda passam
- [ ] Executar `pre-commit run --all-files` e corrigir todos os erros
- [ ] Verificar compatibilidade com Superset 6.1.0 (sem uso de APIs introduzidas após 6.1.0)
- [ ] Garantir que `ENABLE_AI_INTEGRATION=false` (padrão) não afeta comportamento existente

### 5.2 Revisão de Segurança
- [ ] Revisão de todos os itens do checklist em `security-permissions.md`
- [ ] Verificar que nenhuma API key é logada ou exposta
- [ ] Revisão de possíveis vetores de prompt injection

### 5.3 Pull Request
- [ ] Criar branch `feat/ai-integration` a partir de `master`
- [ ] Seguir template `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] Título: `feat(ai): add AI assistant integration with chat sidebar`
- [ ] Descrever BEFORE/AFTER com screenshots do chat sidebar e settings page

---

## Estimativas de Esforço (referência)

| Fase | Escopo                             | Estimativa  |
|------|------------------------------------|-------------|
| 0    | Fundação e setup                   | 1–2 dias    |
| 1    | Backend completo                   | 8–12 dias   |
| 2    | Frontend completo                  | 8–10 dias   |
| 3    | Settings page                      | 4–6 dias    |
| 4    | Testes e qualidade                 | 4–6 dias    |
| 5    | Preparação upstream                | 2–3 dias    |
| **Total** |                               | **~30–40 dias** |

---

## Ordem Sugerida de Implementação

```
Fase 0 (setup)
    │
    ├──► Fase 1.1 + 1.2 (models + permissões)
    │         │
    │         ▼
    │    Fase 1.3 (providers)
    │         │
    │         ▼
    │    Fase 1.4 (tools)
    │         │
    │         ▼
    │    Fase 1.5 (orchestrator)
    │         │
    │         ▼
    │    Fase 1.6 (API REST)
    │
    └──► Fase 2.1 + 2.2 (store + context hook)  ← paralelo com backend
              │
              ▼
         Fase 2.3–2.5 (hooks + componentes)
              │
              ▼
         Fase 2.6 (integração no layout)
              │
              ▼
         Fase 3 (settings page)
              │
              ▼
         Fase 4 (testes e observabilidade)
              │
              ▼
         Fase 5 (PR upstream)
```
