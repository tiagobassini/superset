# AI Integration Plugin — Visão Geral e Arquitetura

## Objetivo

Integrar ferramentas de IA (OpenAI/ChatGPT, Ollama, DeepSeek, Codex e outros provedores compatíveis) ao Apache Superset por meio de uma interface de chat flutuante lateral, permitindo que usuários autorizados interajam com a IA para criar e editar dashboards, charts, datasets e queries SQL — sempre com confirmação explícita do usuário antes de qualquer ação destrutiva ou de escrita.

## Princípios de Design

- **Segurança primeiro**: a IA nunca acessa bancos de dados diretamente. Toda interação com dados passa pelas ferramentas internas do Superset (SQL Lab, APIs REST).
- **Confirmação obrigatória**: qualquer ação de criação, edição ou deleção exige aprovação explícita do usuário antes de ser executada.
- **Compatibilidade**: o plugin deve ser compatível com Superset 6.1.0 e mantido de forma a não quebrar atualizações futuras (fork → potencial PR upstream).
- **Contexto dinâmico**: a IA recebe o contexto da tela atual do usuário, mas não é limitada a ele.
- **Extensibilidade**: novos provedores de IA e novas ferramentas (tools) devem poder ser adicionados sem refatoração estrutural.
- **Histórico por sessão**: o histórico de conversas é armazenado na sessão do browser (sessionStorage), com arquitetura preparada para persistência em banco futuramente.

---

## Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Frontend)                        │
│                                                                  │
│  ┌──────────────────────────────┐   ┌────────────────────────┐  │
│  │   Superset App (React)       │   │  AI Chat Sidebar       │  │
│  │                              │◄──►  (AIChatPanel)         │  │
│  │  - Dashboard View            │   │                        │  │
│  │  - Explore View              │   │  - Message history     │  │
│  │  - SQL Lab View              │   │  - Model selector      │  │
│  │  - etc.                      │   │  - Input + Send        │  │
│  │                              │   │  - Action confirm UI   │  │
│  └──────────────────────────────┘   └──────────┬─────────────┘  │
│                                                │                 │
└────────────────────────────────────────────────┼─────────────── ┘
                                                 │ HTTP (REST)
                                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Processo Flask (Superset)                     │
│                                                                  │
│  ┌───────────────────────┐                                       │
│  │  /api/v1/ai/  (REST)  │  ← única interface HTTP do plugin    │
│  │  - POST /chat         │    recebe requests do browser        │
│  │  - POST /confirm      │                                       │
│  │  - CRUD /agents       │                                       │
│  └──────────┬────────────┘                                       │
│             │ chamada Python direta (sem HTTP)                   │
│             ▼                                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  AI Orchestrator  (superset/ai/orchestrator.py)          │   │
│  │  - monta system prompt + contexto + tools                │   │
│  │  - executa loop de tool calling com o provedor           │   │
│  │  - separa tools automáticas de tools que precisam        │   │
│  │    de confirmação do usuário                             │   │
│  └──────────┬───────────────────────────────────────────────┘   │
│             │ chamada Python direta (sem HTTP)                   │
│             ▼                                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Tool Registry  (superset/ai/tools/)          [ADAPTER]  │   │
│  │                                                          │   │
│  │  Cada AITool traduz a chamada da IA para o vocabulário   │   │
│  │  interno do Superset. A IA só conhece nome + JSON.       │   │
│  │                                                          │   │
│  │  IA chama:          Tool executa:                        │   │
│  │  list_datasets() → DatasetDAO.find_by_user()             │   │
│  │  run_sql_query()  → SqlLabAPI.execute_sql()              │   │
│  │  create_chart()   → CreateChartCommand.run()             │   │
│  │  list_tables()    → TablesDatabaseCommand.run()          │   │
│  └──────────┬───────────────────────────────────────────────┘   │
│             │ chamada Python direta (sem HTTP)                   │
│             ▼                                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Superset Internals (DAOs, Commands, Managers)           │   │
│  │  - Aplicam RBAC, Row Level Security, regras de negócio   │   │
│  │  - O contexto de segurança do usuário logado é preservado│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTPS (só para provedores externos)
                               ▼
┌──────────────────────────────────────────────────────┐
│               AI Providers (externos)                 │
│                                                       │
│   OpenAI API │ Ollama (local) │ DeepSeek │ Codex ...  │
└──────────────────────────────────────────────────────┘
```

---

## Componentes Principais

### 1. Frontend — AIChatPanel
Barra lateral retráctil à direita, presente em todas as páginas do Superset para usuários autorizados. Detalhe em [`frontend-chat-sidebar.md`](./frontend-chat-sidebar.md).

### 2. Backend — AI API (`/api/v1/ai/`)
Endpoints REST que recebem mensagens do usuário, despacham para o orquestrador e retornam respostas + ações pendentes de confirmação. Detalhe em [`backend-api-tools.md`](./backend-api-tools.md).

### 3. AI Orchestrator
Camada Python responsável por:
- Adaptar a mensagem do usuário + contexto + ferramentas disponíveis para o formato do provedor (OpenAI function calling, Ollama tools, etc.)
- Executar o loop de tool calling até a resposta final
- Retornar ao frontend tanto a resposta textual quanto as ações que precisam de confirmação

### 4. Tool Registry
Conjunto de funções Python mapeadas como "tools" para os modelos de IA. Cada tool tem:
- Nome, descrição e schema de parâmetros (JSON Schema)
- Flag `requires_confirmation: bool`
- Execução delegada às APIs internas do Superset (nunca ao banco diretamente)

> **Importante — Tools como Adapters (não HTTP):**
> As tools do plugin residem no mesmo processo Flask do Superset (`superset/ai/tools/`).
> Elas chamam diretamente as classes internas do Superset (DAOs, Commands, Managers),
> **não** a REST API via HTTP. Isso evita latência de rede, autenticação redundante e
> dependência circular.
>
> O papel de *adapter* das tools é entre a IA e o Superset:
> - A IA conhece apenas o nome da tool e o JSON de entrada/saída
> - A tool traduz essa chamada para o vocabulário interno do Superset (DAOs, Commands)
> - O Superset executa a operação com todas as suas regras de negócio e segurança
>
> ```
> IA (modelo)           Tool (adapter)               Superset (internals)
> ─────────────────────────────────────────────────────────────────────────
> tool_call:            ListDatasetsTool              DatasetDAO
>   list_datasets() ──► .execute(user, params)  ───► .find_by_user(user)
>                  ◄─── ToolResult(data=[...])  ◄─── [Dataset objects]
> recebe JSON limpo
> ```
>
> Se no futuro o módulo de IA for extraído como serviço separado (microserviço),
> as tools passariam a chamar a REST API do Superset — mas isso seria uma mudança
> de deployment, não de interface, pois o contrato das tools permanece o mesmo.

### 5. Settings — Agents Page
Página de configuração acessível pelo menu Settings (apenas admins/roles autorizados). Detalhe em [`settings-agents-page.md`](./settings-agents-page.md).

---

## Provedores Suportados (MVP)

| Provedor     | Tipo        | Suporte a Tool Calling | Observação                        |
|--------------|-------------|------------------------|-----------------------------------|
| OpenAI       | Cloud API   | Sim (nativo)           | GPT-4o, GPT-4-turbo, etc.         |
| Ollama       | Local/Self  | Sim (modelos recentes) | llama3, mistral, qwen2.5, etc.    |
| DeepSeek     | Cloud API   | Sim                    | API compatível com OpenAI         |
| Anthropic    | Cloud API   | Sim (nativo)           | Claude 3.x                        |
| OpenAI Codex | Cloud API   | Sim                    | Foco em geração de código/SQL     |

Novos provedores podem ser adicionados implementando a interface `AIProviderAdapter`.

---

## Fluxo de uma Interação Típica

```
Usuário digita: "Cria um bar chart de vendas por região usando o dataset sales_data"

1. Frontend envia: { message, context: { page: "dashboard", dashboard_id: 5 }, agent_id: "gpt4o-prod" }

2. Backend (Orchestrator):
   a. Monta o prompt com contexto da tela + histórico + tools disponíveis
   b. Chama o provedor (ex: OpenAI)
   c. Modelo responde com tool_call: create_chart({ dataset: "sales_data", chart_type: "bar", ... })
   d. Orchestrator detecta requires_confirmation = true
   e. NÃO executa ainda — retorna ao frontend a ação pendente

3. Frontend exibe:
   "Vou criar um bar chart com as seguintes configurações: [...]
    ✅ Confirmar  ❌ Cancelar"

4. Usuário clica em Confirmar

5. Frontend reenvia com: { confirm_action_id: "abc123" }

6. Backend executa create_chart() via Charts API do Superset

7. Frontend exibe: "Chart criado com sucesso! [Abrir chart →]"
```

---

## Como Ativar e Desativar o Módulo de IA

O módulo é **desabilitado por padrão** em todas as instalações. A ativação envolve
dois passos independentes: instalar as dependências Python e ligar a feature flag.

### Passo 1 — Instalar as dependências Python

As bibliotecas de IA (`openai`, `anthropic`, `httpx`) são opcionais e não são incluídas
na instalação padrão do Superset. Instale o extra `[ai]`:

```bash
# Instalação direta (virtualenv local)
pip install apache-superset[ai]
```

**Com Docker Compose (recomendado para desenvolvimento):**

O Superset já tem um mecanismo nativo para dependências extras locais: o arquivo
`docker/requirements-local.txt`. Se existir, ele é instalado automaticamente pelo
`docker/docker-bootstrap.sh` a cada inicialização do container.

```bash
# Criar o arquivo (não é versionado — só se aplica ao seu ambiente local)
echo "apache-superset[ai]" > docker/requirements-local.txt

# Reiniciar o container para instalar as dependências
docker compose restart superset
```

Para **desativar** as dependências de IA:

```bash
# Remover o arquivo ou comentar a linha
rm docker/requirements-local.txt
# ou
echo "# apache-superset[ai]" > docker/requirements-local.txt

docker compose restart superset
```

> O arquivo `docker/requirements-local.txt` já está no `.gitignore` do projeto.
> Cada desenvolvedor/ambiente gerencia o próprio sem afetar o repositório.

---

### Passo 2 — Ligar a feature flag

Com as dependências instaladas, habilite a flag `ENABLE_AI_INTEGRATION` no arquivo
de configuração do Superset. Em desenvolvimento com Docker:

**`docker/pythonpath_dev/superset_config_docker.py`** (crie se não existir — não é versionado):

```python
FEATURE_FLAGS = {
    "ENABLE_AI_INTEGRATION": True,
}
```

Sem a flag habilitada, nenhum componente de IA é carregado — nem no frontend
(o painel não aparece) nem no backend (as rotas `/api/v1/ai/` retornam 404).

---

### Resumo dos estados possíveis

| `requirements-local.txt` | `ENABLE_AI_INTEGRATION` | Resultado                                      |
|--------------------------|-------------------------|------------------------------------------------|
| Sem o extra `[ai]`       | `False` (padrão)        | IA completamente ausente — comportamento padrão do Superset |
| Com o extra `[ai]`       | `False` (padrão)        | Dependências instaladas, mas módulo inativo — sem impacto para o usuário |
| Com o extra `[ai]`       | `True`                  | ✅ Módulo ativo — painel de chat visível, API disponível |
| Sem o extra `[ai]`       | `True`                  | ⚠️ Erro no startup — providers não conseguem importar os SDKs |

---

## Compatibilidade e Estratégia de Fork

- O plugin deve ser desenvolvido como uma **extensão bem isolada** do core do Superset
- Arquivos novos: `superset/ai/` (backend), `superset-frontend/src/components/AIChatPanel/` (frontend)
- Modificações no core existente devem ser **mínimas e cirúrgicas** (ex: adicionar o painel ao layout principal, adicionar item no menu Settings)
- Usar feature flag `ENABLE_AI_INTEGRATION` para habilitar/desabilitar toda a funcionalidade
- Isso facilita o upstream PR e garante que usuários sem a feature não sejam afetados

---

## Referências para Implementação

- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Ollama Tool Support](https://ollama.com/blog/tool-support)
- [Superset REST API](https://superset.apache.org/docs/rest-api)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) — considerar para versão futura
