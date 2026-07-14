# Especificação — Página de Configuração de Agentes de IA

## Visão Geral

Uma página dedicada às configurações dos agentes de IA, acessível pelo menu **Settings** do Superset. Disponível apenas para administradores (e roles com permissão `can_manage_ai_agents`).

---

## Acesso via Menu Settings

Adicionar item no menu Settings do Superset:

```
Settings
├── Security
│   ├── List Roles
│   ├── List Users
│   └── ...
├── ...
└── AI Integration          ← NOVO (visível apenas com ENABLE_AI_INTEGRATION=true)
    └── AI Agents           ← Link para /settings/ai/agents
```

A entrada no menu deve usar a mesma API de extensão de menu do Superset (Flask-AppBuilder menu items) para minimizar modificações no core.

---

## Página: Lista de Agentes (`/settings/ai/agents`)

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  AI Agents                               [+ Add Agent]      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Nome              │ Provedor  │ Modelo   │ Status  │ Ações │
│  ├───────────────────┼───────────┼──────────┼─────────┼──────┤
│  │ GPT-4o Produção   │ OpenAI    │ gpt-4o   │ ✅ Ativo │ ✏️ 🗑️ │
│  │ Ollama Local      │ Ollama    │ llama3.2 │ ✅ Ativo │ ✏️ 🗑️ │
│  │ DeepSeek Coder    │ DeepSeek  │ deepseek │ ⏸ Inativo│ ✏️ 🗑️ │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Ações por linha
- **Editar (✏️)**: abre modal de edição
- **Deletar (🗑️)**: confirmação antes de deletar
- **Toggle de status**: ativar/desativar agente sem deletar

---

## Modal: Criar / Editar Agente

```
┌───────────────────────────────────────────────────────────┐
│  Novo Agente de IA                                   [×]  │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  Nome *                                                   │
│  ┌─────────────────────────────────────────────────┐     │
│  │ GPT-4o Produção                                 │     │
│  └─────────────────────────────────────────────────┘     │
│                                                           │
│  Provedor *                                               │
│  ┌─────────────────────────────────────────────────┐     │
│  │ OpenAI                                        ▼ │     │
│  └─────────────────────────────────────────────────┘     │
│  (OpenAI | Ollama | DeepSeek | Anthropic | Codex)        │
│                                                           │
│  Modelo *                                                 │
│  ┌─────────────────────────────────────────────────┐     │
│  │ gpt-4o                                          │     │
│  └─────────────────────────────────────────────────┘     │
│  💡 Para Ollama, o modelo deve estar disponível localmente │
│                                                           │
│  API Key                           [👁 Mostrar]           │
│  ┌─────────────────────────────────────────────────┐     │
│  │ ••••••••••••••••••••••••••••••••••              │     │
│  └─────────────────────────────────────────────────┘     │
│  ℹ️ Deixe em branco para manter a chave atual            │
│                                                           │
│  URL Base (opcional)                                      │
│  ┌─────────────────────────────────────────────────┐     │
│  │ http://localhost:11434                          │     │
│  └─────────────────────────────────────────────────┘     │
│  Necessário para Ollama e APIs self-hosted                │
│                                                           │
│  ── Permissões ────────────────────────────────────────── │
│                                                           │
│  Roles com acesso a este agente                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │ Admin ×  │ AI Users ×  │ [+ Adicionar role]     │     │
│  └─────────────────────────────────────────────────┘     │
│  Se vazio, apenas Admins terão acesso                     │
│                                                           │
│  ── Configurações Avançadas ───────────────────────────── │
│                                                           │
│  [ ] Agente padrão (usado quando nenhum for selecionado)  │
│  [ ] Ativo                                                │
│                                                           │
│  ── Permissões de Ferramentas (Tools) ─────────────────── │
│                                                           │
│  Ferramentas que este agente pode usar:                   │
│                                                           │
│  Consultas (sempre habilitadas):                          │
│  [✅] list_databases    [✅] list_datasets                 │
│  [✅] get_dataset_schema [✅] list_charts                  │
│  [✅] list_dashboards   [✅] list_saved_queries            │
│                                                           │
│  Ações de escrita (requerem confirmação do usuário):      │
│  [✅] run_sql_query      [✅] save_sql_query               │
│  [✅] create_chart       [✅] edit_chart                   │
│  [✅] create_dashboard   [✅] edit_dashboard               │
│  [✅] add_chart_to_dashboard [✅] create_dataset           │
│                                                           │
│  ── Teste de Conectividade ────────────────────────────── │
│                                                           │
│  [🔌 Testar Conexão]                                      │
│  ✅ Conexão bem-sucedida — Modelo: gpt-4o                  │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                          [Cancelar]  [Salvar]             │
└───────────────────────────────────────────────────────────┘
```

---

## Seção: Configurações Globais de IA

Uma sub-seção abaixo da lista de agentes para configurações gerais:

```
── Configurações Globais ────────────────────────────────────

Comportamento das Tools

  Execução de SQL (run_sql_query):
  (●) Sempre exige confirmação do usuário  ← padrão seguro
  ( ) Permite execução automática para roles:
      [ Selecionar roles... ▼ ]

  Limite máximo de linhas retornadas por query:
  ┌──────┐
  │ 1000 │
  └──────┘

  Histórico de conversas:
  (●) Apenas sessão do browser (sessionStorage)
  ( ) Persistir no banco de dados
      Retenção: [ 30 dias ▼ ]

  Contexto enviado ao modelo:
  [✅] Enviar página atual automaticamente
  [✅] Incluir lista de datasets disponíveis no system prompt
  [ ] Incluir esquema das colunas dos datasets no system prompt
      ⚠️ Pode expor nomes de colunas sensíveis ao provedor externo

───────────────────────────────────────────────────────────

                                             [Salvar Configurações]
```

---

## Estrutura de Arquivos Frontend

```
superset-frontend/src/pages/AIAgentsSettings/
├── index.tsx                     # Ponto de entrada
├── AIAgentsSettings.tsx          # Página principal com lista
├── AIAgentsSettings.test.tsx
├── components/
│   ├── AgentsList.tsx            # Tabela de agentes (reutiliza ListView do Superset)
│   ├── AgentModal.tsx            # Modal criar/editar
│   ├── AgentFormFields.tsx       # Campos do formulário
│   ├── ToolsPermissions.tsx      # Checkboxes de tools
│   ├── GlobalSettings.tsx        # Seção de configurações globais
│   └── ConnectionTestButton.tsx  # Botão + resultado do teste
└── hooks/
    ├── useAgentsCRUD.ts          # Operações CRUD via API
    └── useGlobalAISettings.ts    # Leitura/escrita das configurações globais
```

---

## Rota

```typescript
// superset-frontend/src/routes.tsx — adicionar:
{
  path: '/settings/ai/agents',
  component: lazy(() => import('src/pages/AIAgentsSettings')),
  permission: 'can_manage_ai_agents',
}
```

---

## Validações do Formulário

| Campo     | Regra                                                               |
|-----------|---------------------------------------------------------------------|
| Nome      | Obrigatório, máx 256 chars, único por organização                  |
| Provedor  | Obrigatório, deve ser um dos valores suportados                     |
| Modelo    | Obrigatório, string livre (validado no teste de conexão)            |
| API Key   | Obrigatório na criação; opcional na edição (mantém a atual)         |
| URL Base  | Obrigatório para Ollama; deve ser URL válida com http/https         |
| Roles     | Opcional; se vazio, apenas Admin tem acesso                         |

---

## Configurações Globais — Modelo de Dados

Armazenadas na tabela `key_value` do Superset (ou em `superset_config`) com prefixo `ai_`:

```python
AI_GLOBAL_SETTINGS_DEFAULTS = {
    "ai_sql_confirmation_mode": "always",       # "always" | "roles_only"
    "ai_sql_confirmation_roles": [],            # list[str] de role names
    "ai_max_query_rows": 1000,
    "ai_history_storage": "session",            # "session" | "database"
    "ai_history_retention_days": 30,
    "ai_send_page_context": True,
    "ai_include_datasets_in_prompt": True,
    "ai_include_schema_in_prompt": False,
}
```
