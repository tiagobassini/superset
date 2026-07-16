# Tarefas de Desenvolvimento — AI Integration Plugin

> Referência: [overview.md](./overview.md) | [frontend-chat-sidebar.md](./frontend-chat-sidebar.md) | [backend-api-tools.md](./backend-api-tools.md) | [settings-agents-page.md](./settings-agents-page.md) | [security-permissions.md](./security-permissions.md) | [autonomous-analytics-workflows.md](./autonomous-analytics-workflows.md) | [multilingual-autonomous-discovery.md](./multilingual-autonomous-discovery.md)

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
- [x] Criar `AIProviderAdapter` (ABC) em `superset/ai/providers/base.py`
- [x] Implementar `OpenAIProviderAdapter` (OpenAI + DeepSeek + Codex via `base_url`)
- [x] Implementar `OllamaProviderAdapter` (API REST do Ollama)
- [x] Implementar `AnthropicProviderAdapter`
- [x] Método `test_connection()` em cada adapter
- [x] Testes unitários para cada adapter (com mock das APIs externas)

### 1.4 Tool Registry
- [x] Criar `AITool` base class em `superset/ai/tools/base.py`
- [x] Criar `ToolRegistry` singleton em `superset/ai/tools/registry.py`
- [x] Implementar tools de **consulta** (sem confirmação):
  - [x] `ListDatabasesTool`
  - [x] `ListDatabaseTablesTool` — lista tabelas de um banco via API de schema do Superset (mesmo endpoint usado pelo SQL Lab para autocomplete)
  - [x] `GetTableSchemaTool` — retorna colunas/tipos de uma tabela do banco sem precisar de dataset configurado
  - [x] `ListDatasetsTool`
  - [x] `GetDatasetSchemaTool`
  - [x] `ListChartsTool`
  - [x] `ListDashboardsTool`
  - [x] `ListSavedQueriesTool`
- [x] Implementar tools de **escrita** (com confirmação):
  - [x] `RunSQLQueryTool` — usa API do SQL Lab
  - [x] `SaveSQLQueryTool`
  - [x] `CreateChartTool`
  - [x] `EditChartTool`
  - [x] `CreateDashboardTool`
  - [x] `EditDashboardTool`
  - [x] `AddChartToDashboardTool`
  - [x] `CreateDatasetTool`
- [x] Testes unitários para cada tool (verificar autorização + execução)

### 1.5 AI Orchestrator
- [x] Implementar `AIOrchestrator` em `superset/ai/orchestrator.py`
- [x] Lógica de montagem do system prompt com contexto dinâmico
- [x] Loop de tool calling (executar tools sem confirmação, acumular tools com confirmação)
- [x] Cache de `PendingAction` com TTL de 10 min (usando cache do Superset)
- [x] Método `confirm_and_execute(action_id)` para execução pós-confirmação
- [x] Sanitização de strings externas antes de incluir no prompt
- [x] Testes unitários com mocks do provedor

### 1.6 API REST
- [x] Implementar `AIRestApi` em `superset/ai/api.py` (herdar de `BaseSupersetView`)
- [x] `POST /api/v1/ai/chat` — com validação de schema via Marshmallow
- [x] `POST /api/v1/ai/confirm_action`
- [x] `GET /api/v1/ai/agents`
- [x] `GET /api/v1/ai/agents/<id>` (admin)
- [x] `POST /api/v1/ai/agents` (admin)
- [x] `PUT /api/v1/ai/agents/<id>` (admin)
- [x] `DELETE /api/v1/ai/agents/<id>` (admin)
- [x] `POST /api/v1/ai/agents/<id>/test` (admin)
- [x] Registrar `AIRestApi` no `superset/app.py` (condicionado à feature flag)
- [ ] Testes de integração para todos os endpoints

---

## Fase 2 — Frontend Core

### 2.1 Store / State Management
- [x] Criar `aiChatSlice.ts` com estado: `isOpen`, `messages`, `selectedAgentId`, `isLoading`, `currentContext`
- [x] Adicionar slice ao Redux store do Superset
- [x] Criar `sessionStorage.ts` para persistência do histórico
- [x] Definir todos os tipos TypeScript em `store/types.ts`

### 2.2 Hook de Contexto
- [x] Implementar `useAIContext.ts` — extrai contexto da página atual via URL + Redux
  - [x] Dashboard: `dashboard_id`, `dashboard_title`
  - [x] Explore: `chart_id`, `datasource_id`, `viz_type`
  - [x] SQL Lab: `database_id`, SQL atual
  - [x] Demais: `{ page: 'other' }`

### 2.3 Hook de Agentes
- [x] Implementar `useAgents.ts` — carrega lista de agentes de `GET /api/v1/ai/agents`
- [x] Cache local dos agentes (evitar requests repetidos)

### 2.4 Hook Central do Chat
- [x] Implementar `useAIChat.ts`:
  - [x] `sendMessage(text)` → POST /api/v1/ai/chat
  - [x] `confirmAction(actionId)` → POST /api/v1/ai/confirm_action
  - [x] `cancelAction(actionId)`
  - [x] Gerenciamento do histórico (sessionStorage)
  - [x] Estado de loading por mensagem.
  - [x] Testes unitários do hook, incluindo erro de rede, confirmação e cancelamento.

### 2.5 Componentes do Chat
- [x] `ToggleButton.tsx` — botão flutuante para abrir o painel, estilizado com tokens do tema.
- [x] `ChatHeader.tsx` — controles para minimizar e fechar o painel.
- [x] `ModelSelector.tsx` — usa `Select` padrão e apresenta apenas agentes ativos.
- [x] `MessageBubble.tsx` — renderiza bolhas por papel da mensagem e as ações pendentes associadas.
- [x] `ActionConfirmation.tsx` — apresenta parâmetros, estados de execução, resultado e ações de confirmar/cancelar integradas ao hook.
- [x] `ContextBadge.tsx` — exibe o contexto atual como somente leitura.
- [x] `MessageList.tsx` — lista rolável com scroll automático e confirmações inline.
- [x] `ChatInput.tsx` — textarea padrão, envio por botão/Ctrl+Enter, limpeza de histórico e bloqueio durante carregamento.
- [x] `AIChatPanel.tsx` — integra confirmação de ações, estados de carregamento/erro do hook e sidebar lateral.
- [x] Testes unitários para componentes principais

### 2.6 Integração no Layout
- [x] Identificar o componente raiz de layout do Superset
- [x] Injetar `<AIChatPanel />` condicionado à feature flag
- [x] Ajustar `padding-right` do layout quando painel estiver aberto (380 px em desktop)
- [x] Garantir que o painel não sobreponha conteúdo em nenhuma resolução (em telas até 900 px o chat é uma visualização de tela cheia e o conteúdo principal é ocultado enquanto ele estiver aberto)

### 2.7 Acessibilidade
- [x] `role="complementary"` e `aria-label` no painel
- [x] `aria-live="polite"` na lista de mensagens
- [x] `Esc` fecha o painel
- [x] `Ctrl+Enter` envia mensagem
- [x] Foco movido para o input ao abrir o painel

---

## Fase 3 — Settings Page

### 3.1 Página de Listagem de Agentes
- [x] Criar `AIAgentsSettings.tsx` usando `ListView` do Superset
- [x] Colunas: Nome, Provedor, Modelo, Status, Ações (editar/deletar)
- [x] Botão "Add Agent"
- [x] Toggle ativar/desativar sem deletar

### 3.2 Modal Criar/Editar Agente
- [x] `AgentModal.tsx` com formulário completo
- [x] Campos: Nome, Provedor, Modelo, API Key (mascarada), URL Base
- [x] Seção de Roles com permissão
- [x] Checkboxes de Tools habilitadas
- [x] Botão "Testar Conexão" com feedback
- [x] Validação de formulário (campo obrigatórios, URL válida)

### 3.3 Configurações Globais
- [x] `GlobalSettings.tsx` com opções de comportamento
- [x] Modo de confirmação de SQL (sempre / por role)
- [x] Limite de linhas de query
- [x] Storage do histórico (session / banco)
- [x] Opções de contexto enviado ao modelo

### 3.4 Integração no Menu Settings
- [x] Adicionar item "AI Agents" no menu Settings do Superset
- [x] Visível apenas com `ENABLE_AI_INTEGRATION=true` e `can_manage_ai_agents`
- [x] Rota `/settings/ai/agents` registrada no router

---

## Fase 4 — Qualidade e Observabilidade

### 4.1 Testes
- [x] Cobertura de testes unitários ≥ 80% para `superset/ai/`
- [x] Testes de integração para todos os endpoints de API
- [x] Testes de componente React para `AIChatPanel` e `AIAgentsSettings`
- [x] Testes E2E (Playwright) para fluxo completo:
  - Abrir painel, enviar mensagem, confirmar ação, ver resultado
  - Criar agente na página de settings, testar conexão

### 4.2 Auditoria e Logging
- [x] Log de todas as ações de escrita executadas via IA
- [x] Log de falhas de autorização (tentativas bloqueadas)
- [x] Integrar com o `event_logger` existente do Superset

### 4.3 Documentação
- [x] Docstrings em todas as classes e métodos públicos Python
- [x] Comentários TSDoc nos hooks e componentes principais
- [x] Atualizar `UPDATING.md` com a nova feature flag
- [x] Guia de configuração rápida (primeiros passos para habilitar e configurar um agente)

---

## Fase 5 — Preparação para PR Upstream

### 5.1 Compatibilidade
- [ ] Verificar que todos os testes existentes do Superset ainda passam
- [ ] Executar `pre-commit run --all-files` e corrigir todos os erros
- [x] Verificar compatibilidade com Superset 6.1.0 (sem uso de APIs introduzidas após 6.1.0)
- [x] Garantir que `ENABLE_AI_INTEGRATION=false` (padrão) não afeta comportamento existente

### 5.2 Revisão de Segurança
- [x] Revisão de todos os itens do checklist em `security-permissions.md`
- [x] Verificar que nenhuma API key é logada ou exposta
- [x] Revisão de possíveis vetores de prompt injection

### 5.3 Pull Request
- [ ] Criar branch `feat/ai-integration` a partir de `master`
- [ ] Seguir template `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] Título: `feat(ai): add AI assistant integration with chat sidebar`
- [ ] Descrever BEFORE/AFTER com screenshots do chat sidebar e settings page

---

## Fase 6 — Workflows Analíticos Autônomos

Especificação: [`autonomous-analytics-workflows.md`](autonomous-analytics-workflows.md).

### 6.1 Planejamento de Intenção
- [x] Criar `AnalyticsTaskPlanner` e modelos tipados de intenção, plano e etapa
- [x] Interpretar tema, fonte, métrica, dimensão temporal e destino
- [x] Cobrir sinônimos em pt-BR para criar/adicionar/publicar gráficos
- [x] Resolver nomes ambíguos por busca de recurso; pedir esclarecimento apenas quando indispensável
- [x] Substituir a filtragem exclusiva por palavras-chave pela seleção baseada no plano

### 6.2 Descoberta e Perfil de Dados
- [x] Implementar busca e pontuação de bancos, tabelas, datasets e dashboards candidatos
- [x] Implementar ferramenta segura `profile_dataset` ou `analyze_table` com agregações e limites rígidos
- [x] Identificar colunas candidatas de data, dimensão, identificador e medida
- [x] Respeitar RBAC, datasource permissions, RLS e limite de linhas em toda leitura
- [x] Registrar justificativa da fonte escolhida no plano

### 6.3 Especificação e Validação de Recursos
- [x] Criar contrato tipado para especificação de chart e adaptador para `params` do Superset
- [x] Validar datasource, métrica, dimensão temporal, JSON de chart e destino antes da confirmação
- [x] Suportar fluxo banco/tabela → dataset → chart → dashboard
- [x] Exibir uma confirmação única para o conjunto de ações de escrita do plano
- [x] Tornar plano confirmado imutável, idempotente e interrompível por falha

### 6.4 Progresso Incremental no Chat
- [x] Criar estados `planning`, `discovering`, `analyzing`, `awaiting_confirmation`, `executing`, `awaiting_user_input`, `completed` e `failed`
- [x] Expor tarefas e eventos por SSE, com polling como fallback
- [x] Persistir tarefa/eventos para reconexão após recarregar a página
- [x] Atualizar uma única mensagem de progresso no chat, sem poluir o histórico
- [x] Manter animação de loading durante processamento e removê-la apenas em espera, conclusão ou falha
- [x] Exibir resumo final com achados, recursos criados e links

### 6.5 Segurança, Auditoria e Testes
- [x] Revalidar permissões antes de cada etapa de escrita e isolar tarefas por usuário/agente
- [x] Expirar planos pendentes e impedir confirmações/executações duplicadas
- [x] Auditar criação, confirmação, cancelamento, bloqueio, conclusão e falha de tarefas
- [x] Testes unitários de planejamento, descoberta, validação e estados
- [x] Testes de integração de SSE/polling, expiração, autorização e reconexão
- [x] Testes E2E do fluxo completo e de falhas intermediárias

---

## Fase 7 — Descoberta Multilíngue e Planos Analíticos Autônomos

Especificação: [`multilingual-autonomous-discovery.md`](multilingual-autonomous-discovery.md).

> Esta fase corrige a lacuna observada no primeiro prompt do chat: para um
> pedido como “elabore um gráfico em barras das vendas por ano”, o assistente
> deve pesquisar as fontes acessíveis antes de pedir o nome de uma tabela.
> Nenhum nome ou conteúdo armazenado no banco será alterado.

### 7.1 Normalização e expansão multilíngue do tema
- [x] Criar um contrato tipado de `DiscoveryQuery` com tema, idioma do prompt, sinônimos e termos expandidos.
- [x] Normalizar texto somente em memória: caixa, acentos, pontuação, separadores (`_`, `-`, espaço), singular/plural e tokens compostos.
- [x] Expandir o tema entre pt-BR, en-US, es-ES e fr-FR, sem traduzir ou modificar nomes persistidos de bancos, tabelas, datasets ou consultas salvas.
- [x] Combinar dicionário versionado de termos analíticos comuns (por exemplo, `vendas` ↔ `sales` ↔ `ventas` ↔ `ventes`) com expansão semântica limitada do provedor.
- [x] Limitar tamanho, quantidade de termos e tempo da expansão; falhas do provedor devem degradar para a busca lexical local.
- [x] Testar normalização e equivalências entre os quatro idiomas, incluindo nomes como `international_sales`, `vendas-internacionais`, `ventes_annuelles` e `ventas por año`.

### 7.2 Índice de descoberta seguro e pontuação de fontes
- [ ] Criar serviço de descoberta que pesquise, sob as permissões do usuário, bancos, tabelas, datasets e saved queries.
- [ ] Pesquisar nomes, descrições, schemas/colunas permitidos e metadados seguros, inclusive quando o nome da fonte não tiver relação com o tema solicitado.
- [ ] Pontuar correspondências encontradas em colunas de tabelas/datasets e em colunas inferidas do retorno de saved queries, sem depender da correspondência no nome da fonte.
- [ ] Para saved queries, analisar o SQL já autorizado e/ou schema de resultado limitado para obter aliases, tabelas de origem e colunas; nunca enviar dados brutos, credenciais ou SQL sensível ao modelo.
- [ ] Aplicar ranking determinístico por correspondência exata, normalizada, sinônimos multilíngues, compatibilidade de schema e contexto da página.
- [ ] Identificar em cada candidato colunas adequadas para tempo, métrica, dimensão e identificador antes de propor um gráfico.
- [ ] Deduplicar recursos que representam a mesma fonte e registrar a justificativa/rastreabilidade da pontuação.
- [ ] Manter RBAC, permissões de datasource, RLS e escopo de saved queries em todas as buscas e perfis.
- [ ] Testar ranking, isolamento entre usuários e ausência de vazamento de recursos sem permissão.

### 7.3 Resolução de ambiguidade e proposta ao usuário
- [ ] Definir limiar de confiança e margem entre candidatos para seleção automática segura.
- [ ] Quando houver uma fonte claramente superior, selecioná-la e informar resumidamente o motivo no plano.
- [ ] Quando houver empate ou confiança insuficiente, apresentar até três candidatos com nome, tipo, banco, colunas relevantes e justificativa, pedindo que o usuário escolha.
- [ ] Não perguntar “qual é a tabela?” antes de executar a descoberta; entrar em `awaiting_user_input` apenas após apresentar alternativas concretas ou constatar ausência de fontes.
- [ ] Aceitar a escolha do usuário por nome, índice ou referência inequívoca e retomar o mesmo plano sem repetir a descoberta desnecessariamente.
- [ ] Criar testes unitários e E2E para seleção automática, ambiguidade e nenhuma fonte encontrada.

### 7.4 Planejamento determinístico de ponta a ponta
- [ ] Fazer o backend transformar a fonte escolhida e a intenção em um `AIExecutionPlan` validado, sem delegar ao modelo a montagem de payloads do Superset.
- [ ] Planejar leituras, perfil agregado, criação/reuso de dataset, especificação de chart, criação/reuso de dashboard e publicação conforme necessário.
- [ ] Gerar especificação de chart a partir das colunas efetivamente verificadas e validar datasource, métrica, dimensão temporal, viz type e destino antes de exibir confirmação.
- [ ] Permitir que o Ollama auxilie na interpretação, priorização e narrativa, mas impedir respostas textuais que substituam chamadas/etapas estruturadas do plano.
- [ ] Exibir um único plano legível com fontes, achados, recursos a criar/editar e efeitos esperados; nenhuma escrita é iniciada antes da aprovação explícita.
- [ ] Testar o pedido genérico “elabore um gráfico em barras das vendas por ano” até a apresentação do plano, sem exigir nome de tabela na primeira interação.

### 7.5 Aprovação única, execução e retorno ao chat
- [ ] Fazer a confirmação aprovar o plano imutável completo, e não apenas uma ação isolada, com opção de cancelar antes da execução.
- [ ] Executar as etapas de escrita de forma idempotente e sequencial após aprovação; interromper com erro por etapa e não continuar após falha.
- [ ] Publicar progresso parcial no chat durante descoberta, planejamento e execução, preservando a animação enquanto houver trabalho pendente.
- [ ] Exibir resultado final com fontes selecionadas, decisões, recursos criados/reutilizados, links e falhas acionáveis.
- [ ] Testar ponta a ponta com fontes em inglês, português, espanhol e francês, inclusive o fluxo dataset/tabela ou saved query → chart → dashboard.
- [ ] Medir tokens, latência e número de chamadas; garantir que a descoberta/ranking local reduza o contexto enviado ao Ollama.

### 7.6 Catálogo de metadados e atualização de temas (otimização posterior)
- [ ] Definir um catálogo derivado e não autoritativo **por fonte**, e não uma lista fechada de temas, contendo somente metadados seguros, termos normalizados, idiomas detectados, colunas relevantes e versão/frescor.
- [ ] Popular e atualizar o catálogo a partir de schemas e saved queries já acessíveis, sem alterar os objetos originais do Superset nem seus dados.
- [ ] Inferir temas no momento da indexação ou da consulta a partir dos metadados da fonte; um tema solicitado pela primeira vez não depende de pré-cadastro e não cria uma regra de exclusão.
- [ ] Sempre combinar candidatos do catálogo com fontes novas, ausentes, expiradas ou possivelmente alteradas obtidas por descoberta ao vivo; uma fonte não catalogada nunca pode ser descartada apenas por essa condição.
- [ ] Invalidar por TTL, alteração de dataset/database/saved query, sincronização de metadados e ação manual do administrador; quando o frescor for desconhecido, executar descoberta ao vivo.
- [ ] Usar o catálogo apenas como pré-seleção/ranking. A validação final de schema, permissões e existência deve ser sempre ao vivo antes de gerar ou executar o plano.
- [ ] Medir ganho de latência e tokens contra a descoberta ao vivo; manter a descoberta ao vivo como fallback seguro.
- [ ] Implementar esta subtarefa somente após os critérios funcionais das tarefas 7.1–7.5 estarem atendidos e medidos.

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
