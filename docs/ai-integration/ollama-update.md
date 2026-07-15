# Especificação de atualização do Ollama e do plug-in de IA do Superset

## 1. Objetivo

Implemente uma arquitetura otimizada para o Ollama e para o plug-in de IA integrado ao Apache Superset, priorizando:

- redução do consumo de tokens;
- redução de latência e uso de memória;
- execução confiável de fluxos completos em uma única solicitação do usuário;
- suporte a múltiplas chamadas de ferramentas na mesma interação;
- consulta de dados;
- criação ou reutilização de dataset;
- criação de chart;
- criação ou atualização de dashboard;
- inclusão do chart no dashboard;
- resposta final curta e estruturada;
- preservação de segurança, permissões e isolamento do usuário autenticado.

O sistema atual utiliza `qwen3:1.7b`, possui 16 ferramentas habilitadas e as definições completas dessas ferramentas consomem aproximadamente 3.626 tokens antes mesmo de considerar prompt de sistema, mensagem do usuário, histórico, resultados das ferramentas e resposta final.

A implementação não deve simplesmente aumentar o contexto. O principal objetivo é evitar que as 16 definições sejam enviadas ao modelo em todas as etapas.

---

## 2. Restrições atuais de infraestrutura

Considere a configuração atual:

```yaml
ollama:
  image: ollama/ollama:latest
  profiles:
    - ai
  restart: unless-stopped
  ports:
    - "127.0.0.1:${OLLAMA_PORT:-11434}:11434"
  environment:
    OLLAMA_KEEP_ALIVE: ${OLLAMA_KEEP_ALIVE:-5m}
    OLLAMA_MAX_LOADED_MODELS: "1"
    OLLAMA_CONTEXT_LENGTH: ${OLLAMA_CONTEXT_LENGTH:-8192}
    OLLAMA_NUM_PARALLEL: "1"
    OLLAMA_MAX_QUEUE: "10"
  volumes:
    - ollama:/root/.ollama
  cpus: "8.0"
  mem_limit: 3750m
  mem_reservation: 2g
  depends_on:
    nginx:
      condition: service_started
    superset:
      condition: service_healthy
    superset-websocket:
      condition: service_started
    superset-node:
      condition: service_healthy
    superset-worker:
      condition: service_started
    superset-worker-beat:
      condition: service_started
  healthcheck:
    test: ["CMD", "ollama", "list"]
    interval: 10s
    timeout: 5s
    retries: 12

ollama-pull:
  image: ollama/ollama:latest
  profiles:
    - ai
  restart: "no"
  entrypoint: ["/bin/sh", "-c"]
  command: ["ollama pull ${OLLAMA_MODEL:-qwen3:1.7b}"]
  depends_on:
    ollama:
      condition: service_healthy
  environment:
    OLLAMA_HOST: ollama:11434
  volumes:
    - ollama:/root/.ollama
```

Limites a respeitar:

- execução prioritariamente em CPU;
- limite de memória de aproximadamente 3,75 GB;
- somente um modelo carregado;
- somente uma requisição paralela por modelo;
- contexto configurado inicialmente em 8.192 tokens;
- não aumentar o contexto global sem medição de memória;
- não habilitar paralelismo maior que 1;
- não carregar simultaneamente um modelo de planejamento e outro de execução.

---

## 3. Resultado arquitetural esperado

A solicitação do usuário deve continuar sendo uma única interação do ponto de vista da interface:

> Consulte a quantidade de alvarás emitidos por ano, crie o dataset, gere um gráfico de linhas e adicione ao dashboard Alvarás.

Internamente, o backend deve coordenar várias etapas:

```text
Solicitação do usuário
        |
        v
Classificador determinístico de intenção
        |
        v
Seleção do menor conjunto de ferramentas necessário
        |
        v
Criação de plano estruturado
        |
        v
Execução sequencial das ferramentas
        |
        v
Validação de cada resultado
        |
        v
Recuperação ou correção em caso de erro
        |
        v
Resposta final resumida
```

O modelo deve conseguir concluir, dentro da mesma execução lógica:

1. identificar o banco ou dataset;
2. obter somente os metadados necessários;
3. gerar e validar uma consulta SQL;
4. opcionalmente executar uma consulta de amostra;
5. criar ou reutilizar um dataset;
6. criar um chart;
7. localizar ou criar um dashboard;
8. adicionar o chart ao dashboard;
9. confirmar o resultado ao usuário.

A aplicação, e não o modelo, deve manter o estado do workflow.

---

## 4. Não enviar as 16 ferramentas em todas as chamadas

### 4.1. Criar catálogo interno de ferramentas

Mantenha as 16 ferramentas registradas no backend, mas não envie todas ao Ollama por padrão.

```ts
type ToolCatalogEntry = {
  name: string;
  domain:
    | "metadata"
    | "sql"
    | "dataset"
    | "chart"
    | "dashboard"
    | "navigation"
    | "validation";
  summary: string;
  risk: "read" | "write";
  dependencies?: string[];
  tags: string[];
};
```

Exemplo:

```ts
{
  name: "create_chart",
  domain: "chart",
  summary: "Cria um gráfico a partir de um dataset existente.",
  risk: "write",
  dependencies: ["dataset_id"],
  tags: ["chart", "visualization", "superset"]
}
```

O catálogo compacto pode ser usado pelo classificador. Os JSON Schemas completos somente devem ser enviados quando a ferramenta for selecionada.

### 4.2. Implementar seleção dinâmica

Antes de chamar o Ollama, classifique a solicitação usando código determinístico sempre que possível.

```ts
const INTENT_PATTERNS = {
  query_data: [
    "consultar",
    "buscar",
    "mostrar",
    "quantidade",
    "total",
    "média",
    "listar",
  ],
  create_dataset: ["criar dataset", "novo dataset", "salvar consulta"],
  create_chart: ["criar gráfico", "gerar gráfico", "visualização", "chart"],
  dashboard: [
    "dashboard",
    "painel",
    "adicionar ao dashboard",
    "incluir no painel",
  ],
};
```

Para uma solicitação que pede consulta, dataset, gráfico e dashboard, envie somente ferramentas dos domínios necessários.

Metas:

- reduzir de 16 ferramentas para aproximadamente 4 a 8 por etapa;
- manter as definições abaixo de 1.500 tokens na primeira chamada;
- manter chamadas subsequentes abaixo de 1.000 tokens em ferramentas.

### 4.3. Separar descoberta e mutação

Grupo de descoberta/leitura:

- listar bancos;
- localizar dataset;
- obter schema;
- localizar dashboard;
- executar consulta de amostra;
- validar SQL.

Grupo de alteração:

- criar dataset;
- criar chart;
- criar dashboard;
- atualizar dashboard;
- adicionar chart ao dashboard.

Na fase de descoberta, não envie ferramentas de alteração que ainda não possam ser usadas.

---

## 5. Orquestrador com estado fora do contexto

Implemente uma máquina de estados no backend.

```ts
type WorkflowStep =
  | "understand_request"
  | "resolve_database"
  | "resolve_schema"
  | "generate_sql"
  | "validate_sql"
  | "preview_query"
  | "resolve_dataset"
  | "create_dataset"
  | "create_chart"
  | "resolve_dashboard"
  | "create_dashboard"
  | "attach_chart"
  | "finalize";

type WorkflowState = {
  requestId: string;
  userRequest: string;
  currentStep: WorkflowStep;
  completedSteps: WorkflowStep[];
  databaseId?: number;
  datasetId?: number;
  datasetName?: string;
  sql?: string;
  chartId?: number;
  chartName?: string;
  dashboardId?: number;
  dashboardName?: string;
  errors: Array<{
    step: WorkflowStep;
    message: string;
    recoverable: boolean;
  }>;
};
```

Não reenvie o estado completo como texto livre. Envie somente resumo mínimo:

```json
{
  "goal": "create_chart_and_add_to_dashboard",
  "completed": {
    "database_id": 3,
    "dataset_id": 42,
    "sql_validated": true
  },
  "current_step": "create_chart",
  "constraints": {
    "chart_type": "line",
    "dashboard_name": "Alvarás"
  }
}
```

O backend deve:

- decidir a próxima etapa;
- verificar pré-requisitos;
- armazenar IDs;
- impedir repetição de ações concluídas;
- impedir loops infinitos;
- limitar tentativas.

---

## 6. Planejamento estruturado

Não peça uma explicação textual do plano. Use JSON Schema.

```json
{
  "type": "object",
  "properties": {
    "intent": {
      "type": "string",
      "enum": [
        "answer",
        "query",
        "create_dataset",
        "create_chart",
        "create_dashboard_workflow"
      ]
    },
    "requires": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": [
          "database",
          "schema",
          "sql",
          "dataset",
          "chart",
          "dashboard"
        ]
      }
    },
    "chart_type": {
      "type": ["string", "null"],
      "enum": ["table", "bar", "line", "pie", "big_number", null]
    },
    "dashboard_name": {
      "type": ["string", "null"]
    },
    "needs_clarification": {
      "type": "boolean"
    },
    "clarification_question": {
      "type": ["string", "null"]
    }
  },
  "required": [
    "intent",
    "requires",
    "chart_type",
    "dashboard_name",
    "needs_clarification",
    "clarification_question"
  ]
}
```

Não inclua SQL nessa etapa, salvo quando o schema relevante já estiver disponível.

---

## 7. Reduzir schemas das ferramentas

Aplique:

1. remover descrições redundantes;
2. não repetir regras globais em cada ferramenta;
3. trocar parágrafos por frases curtas;
4. remover exemplos dos schemas enviados;
5. usar enums pequenos;
6. remover campos internos;
7. preencher no backend usuário, CSRF, URL-base, headers, owner e defaults;
8. não permitir que o modelo monte URLs;
9. não solicitar IDs já presentes no estado;
10. criar wrappers de alto nível.

Exemplo desejado:

```json
{
  "name": "create_chart",
  "description": "Cria um gráfico para o dataset atual.",
  "parameters": {
    "type": "object",
    "properties": {
      "name": {"type": "string"},
      "type": {
        "type": "string",
        "enum": ["table", "bar", "line", "pie", "big_number"]
      },
      "x": {"type": ["string", "null"]},
      "metric": {"type": "string"}
    },
    "required": ["name", "type", "metric"]
  }
}
```

O backend converte esse payload no payload completo da API do Superset.

---

## 8. Ferramentas compostas

Crie wrappers idempotentes:

### `ensure_dataset`

- procura dataset equivalente;
- reutiliza quando existe;
- cria quando não existe.

Saída compacta:

```json
{
  "dataset_id": 42,
  "dataset_name": "alvaras_por_ano",
  "created": true
}
```

### `ensure_dashboard`

- procura pelo nome ou slug;
- respeita permissões;
- reutiliza ou cria.

### `create_chart_from_dataset`

Entrada:

```json
{
  "name": "Alvarás emitidos por ano",
  "type": "line",
  "x": "ano",
  "metric": "quantidade"
}
```

O `dataset_id` deve ser injetado pelo backend.

### `attach_chart_to_dashboard`

Os IDs devem ser obtidos do estado quando disponíveis.

### `build_visualization_workflow`

Criar opcionalmente uma ferramenta composta para coordenar dataset, chart e dashboard quando SQL e database já estiverem validados.

---

## 9. Descoberta progressiva do schema

Nunca envie todos os bancos, tabelas e colunas.

Fluxo:

1. identificar termos;
2. buscar datasets/tabelas candidatas;
3. selecionar no máximo 3;
4. carregar somente colunas relevantes;
5. incluir relacionamentos apenas para JOIN;
6. enviar schema compacto.

```text
DB: Oracle
Dialect: oracle

TABLE siat.alvara
- id_alvara: integer, primary key
- data_ini_validade: date, emissão/início
- data_fim_validade: date, fim da validade
```

Limites:

```ts
const SCHEMA_LIMITS = {
  maxTables: 3,
  maxColumnsPerTable: 30,
  maxRelationships: 10,
  maxSampleRows: 5,
};
```

---

## 10. Busca lexical antes de embeddings

Implemente inicialmente busca lexical sobre:

- nome do dataset;
- tabela física;
- descrição;
- colunas;
- métricas;
- termos de negócio.

Use normalização e aliases:

```ts
const BUSINESS_ALIASES = {
  emissão: ["data_ini_validade", "data_emissao", "created_at"],
  validade: ["data_fim_validade", "valid_until"],
  alvará: ["alvara", "licenca", "autorizacao"],
};
```

Embeddings podem ser adicionados posteriormente.

---

## 11. Modelfile específico

Criar:

```text
docker/ollama/Modelfile.superset
```

Conteúdo inicial:

```dockerfile
FROM qwen3:1.7b

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 8192
PARAMETER num_predict 700

SYSTEM """
Você é o agente de automação do Apache Superset.

Objetivo:
Interpretar a solicitação e selecionar ferramentas para consultar dados,
criar ou reutilizar datasets, criar gráficos e adicioná-los a dashboards.

Regras:
- Use apenas bancos, datasets, tabelas, colunas e IDs fornecidos.
- Nunca invente identificadores.
- SQL deve ser somente leitura.
- Nunca use INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, CREATE, TRUNCATE ou GRANT.
- Não explique raciocínio interno.
- Não repita uma ferramenta concluída com sucesso.
- Após cada ferramenta, use somente os dados retornados.
- Respostas finais devem ser curtas.
- Quando solicitado JSON, retorne apenas JSON válido.
- Não inclua markdown em argumentos de ferramentas.
"""
```

Não incluir no `SYSTEM` a documentação das 16 ferramentas.

---

## 12. Inicialização do modelo customizado

Substitua ou complemente `ollama-pull`:

```yaml
ollama-init:
  image: ollama/ollama:latest
  profiles:
    - ai
  restart: "no"
  entrypoint: ["/bin/sh", "-c"]
  command:
    - |
      set -eu
      ollama pull "$${OLLAMA_BASE_MODEL}"
      ollama create "$${OLLAMA_MODEL}" -f /config/Modelfile.superset
      ollama show "$${OLLAMA_MODEL}"
  depends_on:
    ollama:
      condition: service_healthy
  environment:
    OLLAMA_HOST: ollama:11434
    OLLAMA_BASE_MODEL: ${OLLAMA_BASE_MODEL:-qwen3:1.7b}
    OLLAMA_MODEL: ${OLLAMA_MODEL:-superset-agent:1.0}
  volumes:
    - ollama:/root/.ollama
    - ./docker/ollama:/config:ro
```

Usar:

```env
OLLAMA_MODEL=superset-agent:1.0
```

Não usar `latest` como tag do modelo customizado.

---

## 13. Ajustes no Compose

Manter:

```yaml
OLLAMA_MAX_LOADED_MODELS: "1"
OLLAMA_NUM_PARALLEL: "1"
OLLAMA_CONTEXT_LENGTH: ${OLLAMA_CONTEXT_LENGTH:-8192}
```

Avaliar:

```yaml
OLLAMA_KEEP_ALIVE: ${OLLAMA_KEEP_ALIVE:-15m}
```

Não aumentar para 16k antes de reduzir ferramentas, compactar resultados e medir RSS/OOM.

O healthcheck principal não deve executar geração pesada a cada intervalo. Crie smoke test separado para validar geração.

---

## 14. Controlar modo de raciocínio

A implementação deve:

- desabilitar pensamento explícito em etapas simples;
- não guardar raciocínio no histórico;
- não mostrar raciocínio ao usuário;
- usar raciocínio somente para JOIN, correção SQL e recuperação complexa.

Quando suportado:

```json
{
  "think": false
}
```

Aplicar em classificação, seleção de ferramenta, extração de parâmetros e resposta final.

Variável:

```env
OLLAMA_ENABLE_THINKING=false
```

---

## 15. Orçamento de tokens

```ts
type TokenBudget = {
  contextLimit: number;
  reservedForOutput: number;
  reservedForToolResults: number;
  maxSystemPrompt: number;
  maxToolDefinitions: number;
  maxHistory: number;
  maxSchema: number;
  maxUserInput: number;
};
```

Configuração inicial:

```ts
const TOKEN_BUDGET: TokenBudget = {
  contextLimit: 8192,
  reservedForOutput: 700,
  reservedForToolResults: 1800,
  maxSystemPrompt: 700,
  maxToolDefinitions: 1500,
  maxHistory: 900,
  maxSchema: 1500,
  maxUserInput: 700,
};
```

Ordem de compactação:

1. remover mensagens antigas;
2. resumir histórico;
3. remover campos desnecessários de resultados;
4. reduzir schema;
5. reduzir ferramentas;
6. dividir em nova chamada interna;
7. nunca remover regras de segurança.

---

## 16. Histórico e memória operacional

Não envie toda a conversa.

```ts
type ConversationMemory = {
  selectedDatabaseId?: number;
  selectedDatasetId?: number;
  selectedDatasetName?: string;
  selectedDashboardId?: number;
  selectedDashboardName?: string;
  lastChartId?: number;
  lastChartName?: string;
  activeFilters?: Record<string, unknown>;
  lastUserGoal?: string;
  summary?: string;
};
```

Envie somente últimas mensagens relevantes, memória operacional e solicitação atual.

---

## 17. Compactar resultados

Exemplo desejado:

```json
{
  "ok": true,
  "dataset_id": 42,
  "dataset_name": "alvaras_por_ano"
}
```

Limites:

- resultado comum até 500 tokens;
- preview SQL até 20 linhas;
- no máximo 10 colunas;
- excluir nulos e metadados HTTP;
- truncar strings longas;
- não retornar layout completo do dashboard.

---

## 18. SQL seguro

Implementar:

1. uma única instrução;
2. somente `SELECT` ou `WITH ... SELECT`;
3. bloqueio de DDL/DML;
4. limite de linhas;
5. timeout;
6. usuário somente leitura;
7. validação de dialect;
8. validação de tabelas e colunas.

Considere `sqlglot`.

```ts
const FORBIDDEN_SQL = [
  "INSERT",
  "UPDATE",
  "DELETE",
  "MERGE",
  "DROP",
  "ALTER",
  "CREATE",
  "TRUNCATE",
  "GRANT",
  "REVOKE",
  "EXEC",
  "EXECUTE",
];
```

Permitir no máximo 2 correções de SQL, enviando apenas SQL anterior, erro sanitizado e schema relevante.

---

## 19. Escolha determinística de gráfico

```ts
function suggestChart(shape: QueryShape): ChartType {
  if (shape.singleMetric && shape.singleRow) return "big_number";
  if (shape.timeDimension && shape.metricCount <= 3) return "line";
  if (shape.categoryDimension && shape.metricCount <= 2) return "bar";
  if (shape.categoryCount <= 6 && shape.partToWhole) return "pie";
  return "table";
}
```

O modelo só deve sobrescrever quando o usuário pedir explicitamente outro tipo.

---

## 20. Idempotência

Antes de criar:

- procurar dataset por nome, SQL normalizado e database;
- procurar dashboard por slug/nome;
- procurar chart por nome, dataset e configuração;
- verificar se o chart já está no dashboard.

```ts
const idempotencyKey = hash({
  userId,
  databaseId,
  normalizedSql,
  chartType,
  chartName,
  dashboardName,
});
```

Impedir duplicação após timeout, reload, retry e repetição de tool call.

---

## 21. Segurança

Todas as ferramentas devem operar no contexto do usuário autenticado.

Validar:

- acesso ao database;
- acesso ao dataset;
- permissão para SQL;
- permissão para criar dataset/chart;
- permissão para editar dashboard;
- Row Level Security;
- schemas e colunas permitidos.

O prompt não é barreira de segurança. Toda autorização deve ocorrer no backend.

---

## 22. Retries e loops

```ts
const AGENT_LIMITS = {
  maxModelCalls: 8,
  maxToolCalls: 12,
  maxRetriesPerStep: 2,
  maxSqlCorrections: 2,
  maxWorkflowDurationMs: 120_000,
};
```

Interromper quando:

- ferramenta e argumentos forem repetidos;
- etapa já estiver concluída;
- limite for atingido;
- ferramenta estiver fora da allowlist;
- erro for não recuperável.

---

## 23. Cliente Ollama centralizado

```ts
type OllamaRequestOptions = {
  model: string;
  messages: unknown[];
  tools?: unknown[];
  format?: object | "json";
  think?: boolean;
  temperature?: number;
  numPredict?: number;
  keepAlive?: string;
};
```

Padrão:

```ts
const DEFAULT_OLLAMA_OPTIONS = {
  model: process.env.OLLAMA_MODEL ?? "superset-agent:1.0",
  think: false,
  temperature: 0.1,
  numPredict: 700,
  keepAlive: process.env.OLLAMA_KEEP_ALIVE ?? "15m",
};
```

Use `stream: false` nas etapas internas estruturadas.

Registre `prompt_eval_count`, `eval_count`, durações, ferramentas enviadas, tool calls e tamanho dos resultados.

---

## 24. Observabilidade

Log:

```json
{
  "event": "ollama_call_completed",
  "request_id": "uuid",
  "workflow_step": "generate_sql",
  "model": "superset-agent:1.0",
  "tool_count": 3,
  "prompt_tokens": 2140,
  "completion_tokens": 187,
  "duration_ms": 8400,
  "success": true
}
```

Métricas:

- tokens por solicitação e etapa;
- latência;
- taxa de sucesso;
- retries;
- SQL inválido;
- duplicações evitadas;
- memória do container;
- tempo de carregamento.

Não registrar credenciais, cookies, tokens ou dados sensíveis.

---

## 25. Testes obrigatórios

### Unitários

- classificador;
- seletor de ferramentas;
- compactadores;
- orçamento;
- SQL;
- máquina de estados;
- idempotência;
- escolha de gráfico;
- allowlist por etapa.

### Integração

1. Consultar sem criar.
2. Criar dataset.
3. Criar chart.
4. Criar dashboard.
5. Reutilizar dashboard.
6. Adicionar chart.
7. Executar fluxo completo.
8. Repetir sem duplicar.
9. Corrigir SQL inválido.
10. Bloquear SQL destrutivo.
11. Negar acesso não autorizado.
12. Recuperar timeout.
13. Encerrar após retries.
14. Manter contexto abaixo de 8.192.

### Cenário principal de aceite

Entrada:

```text
Consulte a quantidade de alvarás emitidos por ano usando a data de início
da validade, crie ou reutilize um dataset chamado alvaras_por_ano, crie um
gráfico de linhas chamado Alvarás emitidos por ano e adicione ao dashboard
Alvarás. Considere somente de 1980 até o ano atual.
```

SQL esperado:

```sql
SELECT
    EXTRACT(YEAR FROM data_ini_validade) AS ano,
    COUNT(*) AS quantidade_alvaras
FROM siat.alvara
WHERE data_ini_validade IS NOT NULL
  AND EXTRACT(YEAR FROM data_ini_validade)
      BETWEEN 1980 AND EXTRACT(YEAR FROM SYSDATE)
GROUP BY EXTRACT(YEAR FROM data_ini_validade)
ORDER BY ano
```

Resultado:

- database autorizado identificado;
- SQL validado;
- dataset criado ou reutilizado;
- chart criado;
- dashboard criado ou reutilizado;
- chart adicionado;
- nenhuma duplicação;
- no máximo 8 chamadas ao modelo;
- no máximo 12 tool calls;
- ferramentas abaixo de 1.500 tokens por chamada;
- contexto abaixo de 8.192 tokens.

---

## 26. Benchmark

Criar script com pelo menos 20 solicitações.

Medir:

- taxa de conclusão;
- tokens de entrada/saída;
- duração;
- chamadas ao modelo;
- ferramentas enviadas;
- tool calls;
- memória máxima;
- erros;
- duplicações.

Metas:

- reduzir em pelo menos 50% tokens de ferramentas;
- reduzir em pelo menos 30% tokens totais;
- completar ao menos 85% dos workflows válidos;
- bloquear 100% dos DDL/DML nos testes;
- não ultrapassar memória;
- não criar duplicatas;
- resposta final abaixo de 250 tokens.

---

## 27. Estratégia de modelo

Primeira versão:

```text
qwen3:1.7b
```

Não trocar antes de concluir seleção dinâmica, compactação, estado, validação e benchmark.

Depois comparar com variante quantizada fixada e `qwen3:4b` somente se houver memória.

Não usar tag flutuante para o modelo-base em produção. Fixar tag e, quando possível, digest.

---

## 28. Fine-tuning

Não implementar na primeira entrega.

Primeiro coletar exemplos anonimizados de workflows, ferramentas escolhidas, argumentos, resultados, sucesso e correções humanas.

Só considerar LoRA/QLoRA com centenas de exemplos revisados e avaliação reproduzível.

---

## 29. Arquivos esperados

Adapte à estrutura real:

```text
docker/ollama/Modelfile.superset
docker-compose.yml
.env.example

src/features/ai/
  ollamaClient.ts
  tokenBudget.ts
  toolCatalog.ts
  toolSelector.ts
  workflow/
    types.ts
    stateMachine.ts
    orchestrator.ts
  tools/
    compactSchemas.ts
    normalizeResults.ts
    ensureDataset.ts
    ensureDashboard.ts
    createChartFromDataset.ts
    attachChartToDashboard.ts
  sql/
    validateSql.ts
    previewSql.ts
  telemetry/
    aiTelemetry.ts

tests/ai/
scripts/benchmark-ai-agent.ts
```

Se a lógica estiver no backend Python, implementar módulos equivalentes em Python.

O navegador não deve chamar o Ollama diretamente.

---

## 30. Ordem de implementação

1. Instrumentar baseline.
2. Criar testes.
3. Compactar schemas.
4. Criar catálogo e seleção dinâmica.
5. Implementar máquina de estados.
6. Compactar resultados.
7. Criar wrappers idempotentes.
8. Validar SQL.
9. Criar Modelfile.
10. Criar `ollama-init`.
11. Implementar orçamento.
12. Prevenir loops.
13. Rodar benchmark.
14. Ajustar `keep_alive`.
15. Avaliar modelo/quantização.
16. Documentar.

---

## 31. Critérios de conclusão

Concluído somente quando:

- uma solicitação inicia o fluxo completo;
- o backend conclui todas as etapas;
- somente ferramentas relevantes são enviadas;
- as 16 ferramentas não são enviadas juntas por padrão;
- o estado fica fora do prompt;
- resultados são compactos;
- SQL é validado;
- ações são idempotentes;
- permissões são respeitadas;
- contexto permanece no limite;
- tokens e latência são medidos;
- testes cobrem o fluxo.

---

## 32. Instruções ao Codex

1. Examine a estrutura real do repositório.
2. Localize cliente Ollama, 16 ferramentas, loop do agente, APIs do Superset e estado do chat.
3. Preserve compatibilidade.
4. Faça mudanças incrementais.
5. Liste arquivos alterados.
6. Execute testes.
7. Mostre benchmark antes/depois.
8. Sinalize limitações.
9. Não afirme sucesso sem testar o fluxo completo.

---

## 33. Referências

- https://docs.ollama.com/faq
- https://docs.ollama.com/context-length
- https://docs.ollama.com/modelfile
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/generate
- https://docs.ollama.com/api/openai-compatibility
- https://ollama.com/library/qwen3:1.7b
