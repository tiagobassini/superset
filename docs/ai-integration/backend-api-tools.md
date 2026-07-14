# Especificação Backend — API e Tool Registry

## Visão Geral

O backend expõe endpoints REST em `/api/v1/ai/` que recebem mensagens do usuário, orquestram a chamada ao provedor de IA com as ferramentas disponíveis e retornam a resposta + ações pendentes. A execução das ações só acontece após confirmação explícita do usuário.

---

## Estrutura de Arquivos

```
superset/ai/
├── __init__.py
├── api.py                    # Endpoints REST (Flask-AppBuilder RestModelView)
├── schemas.py                # Marshmallow schemas (validação + OpenAPI)
├── orchestrator.py           # AI Orchestrator — loop de tool calling
├── exceptions.py             # Exceções específicas do módulo
├── models.py                 # Modelos SQLAlchemy (AIAgent, futuramente AIHistory)
│
├── providers/                # Adaptadores por provedor
│   ├── __init__.py
│   ├── base.py               # Interface AIProviderAdapter (ABC)
│   ├── openai_provider.py    # Adapter OpenAI / Codex / DeepSeek (API OpenAI-compatible)
│   ├── ollama_provider.py    # Adapter Ollama
│   └── anthropic_provider.py # Adapter Anthropic Claude
│
└── tools/                    # Tool Registry
    ├── __init__.py
    ├── registry.py           # ToolRegistry — registro e lookup de tools
    ├── base.py               # Classe base AITool
    ├── datasets.py           # list_datasets, get_dataset_schema
    ├── databases.py          # list_databases, get_database_tables
    ├── queries.py            # run_sql_query, save_sql_query
    ├── charts.py             # list_charts, create_chart, edit_chart
    ├── dashboards.py         # list_dashboards, create_dashboard,
    │                         # edit_dashboard, add_chart_to_dashboard
    └── context.py            # get_current_context (metadados da sessão)
```

---

## Endpoints REST

### POST `/api/v1/ai/chat`

Envia uma mensagem para o agente de IA e retorna a resposta + eventuais ações pendentes de confirmação.

**Request Body:**
```json
{
  "message": "Cria um bar chart de vendas por região",
  "agent_id": "uuid-do-agente",
  "context": {
    "page": "dashboard",
    "resource_id": 5,
    "resource_name": "Sales Overview",
    "metadata": {}
  },
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

**Response 200:**
```json
{
  "response": "Encontrei o dataset sales_data. Vou criar um bar chart com as configurações abaixo:",
  "pending_actions": [
    {
      "id": "action-uuid-123",
      "type": "create_chart",
      "description": "Criar Bar Chart 'Vendas por Região'",
      "params": {
        "datasource_id": 12,
        "datasource_type": "table",
        "viz_type": "bar",
        "slice_name": "Vendas por Região",
        "groupby": ["region"],
        "metrics": ["sum__total_sales"]
      },
      "preview": null,
      "requires_confirmation": true
    }
  ]
}
```

**Erros:**
- `400` — request inválido (schema de validação)
- `403` — usuário sem permissão para usar IA
- `404` — agente não encontrado
- `502` — falha na comunicação com o provedor de IA

---

### POST `/api/v1/ai/confirm_action`

Confirma a execução de uma ação pendente retornada pelo `/chat`.

**Request Body:**
```json
{
  "action_id": "action-uuid-123",
  "agent_id": "uuid-do-agente"
}
```

**Response 200:**
```json
{
  "status": "executed",
  "result": {
    "id": 42,
    "name": "Vendas por Região",
    "url": "/explore/?slice_id=42"
  }
}
```

**Erros:**
- `400` — action_id inválido ou já executada/cancelada
- `403` — usuário sem permissão para esta ação específica
- `404` — action não encontrada ou expirada (TTL de 10 minutos)

---

### GET `/api/v1/ai/agents`

Lista os agentes de IA disponíveis para o usuário atual.

**Response 200:**
```json
{
  "result": [
    {
      "id": "uuid",
      "name": "GPT-4o Produção",
      "provider": "openai",
      "model": "gpt-4o",
      "is_default": true,
      "is_active": true
    },
    {
      "id": "uuid",
      "name": "Ollama Local",
      "provider": "ollama",
      "model": "llama3.2",
      "is_default": false,
      "is_active": true
    }
  ]
}
```

---

### CRUD de Agentes (Settings)

| Método   | Endpoint                    | Descrição                          | Permissão |
|----------|-----------------------------|------------------------------------|-----------|
| `GET`    | `/api/v1/ai/agents`         | Lista agentes ativos               | AI User   |
| `GET`    | `/api/v1/ai/agents/<id>`    | Detalhes de um agente              | Admin     |
| `POST`   | `/api/v1/ai/agents`         | Cria novo agente                   | Admin     |
| `PUT`    | `/api/v1/ai/agents/<id>`    | Atualiza agente existente          | Admin     |
| `DELETE` | `/api/v1/ai/agents/<id>`    | Remove agente                      | Admin     |
| `POST`   | `/api/v1/ai/agents/<id>/test` | Testa conectividade do agente    | Admin     |

---

## AI Orchestrator

```python
# superset/ai/orchestrator.py

class AIOrchestrator:
    """
    Coordena o loop de tool calling entre o provedor de IA e o Tool Registry.
    Não executa ações que requerem confirmação — retorna-as como pendentes.
    """

    def __init__(self, agent: AIAgent, tool_registry: ToolRegistry, user: User):
        self.agent = agent
        self.registry = tool_registry
        self.user = user
        self.provider = self._build_provider(agent)

    def chat(
        self,
        message: str,
        history: list[dict],
        context: PageContext,
    ) -> OrchestratorResult:
        """
        Executa o loop:
        1. Monta system prompt com contexto
        2. Chama o provedor com tools disponíveis
        3. Se provider retorna tool_calls:
           a. Para tools sem confirmação: executa e continua o loop
           b. Para tools com confirmação: armazena como pending_action e para
        4. Retorna texto de resposta + pending_actions
        """
        ...

    def confirm_and_execute(self, action_id: str) -> ActionResult:
        """
        Executa uma ação previamente pendente após confirmação do usuário.
        Busca a ação no cache (Redis ou memória com TTL).
        """
        ...
```

### Cache de Ações Pendentes

Ações pendentes de confirmação são armazenadas no cache do Superset (Redis ou SimpleCache) com TTL de 10 minutos:

```python
PENDING_ACTION_TTL = 600  # segundos

cache_key = f"ai_pending_action:{user_id}:{action_id}"
cache.set(cache_key, action_data, timeout=PENDING_ACTION_TTL)
```

---

## Tool Registry

### Classe Base

```python
# superset/ai/tools/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ToolResult:
    success: bool
    data: Any
    error: str | None = None

class AITool(ABC):
    name: str                    # ex: "create_chart"
    description: str             # Descrição para o modelo de IA
    parameters_schema: dict      # JSON Schema dos parâmetros
    requires_confirmation: bool = False  # Se True, não executa automaticamente

    @abstractmethod
    def execute(self, user: "User", params: dict) -> ToolResult:
        """Executa a tool usando as APIs internas do Superset."""
        ...

    def to_openai_tool(self) -> dict:
        """Serializa para o formato de tool calling da OpenAI."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }
```

### Ferramentas Disponíveis

#### Consulta (sem confirmação)

| Tool                    | Descrição                                                                 |
|-------------------------|---------------------------------------------------------------------------|
| `list_databases`        | Lista databases conectados ao Superset                                    |
| `list_database_tables`  | Lista tabelas disponíveis em um banco conectado (inclui tabelas sem dataset) |
| `get_table_schema`      | Retorna colunas e tipos de uma tabela do banco (sem precisar de dataset)  |
| `list_datasets`         | Lista datasets disponíveis (filtrado por permissão)                       |
| `get_dataset_schema`    | Retorna colunas e tipos de um dataset já configurado no Superset          |
| `list_charts`           | Lista charts existentes                                                   |
| `list_dashboards`       | Lista dashboards existentes                                               |
| `list_saved_queries`    | Lista queries SQL salvas                                                  |
| `get_current_context`   | Retorna contexto da tela atual do usuário                                 |

> **Nota sobre `list_database_tables` e `get_table_schema`**: usam a mesma
> infraestrutura de introspecção de schema que o SQL Lab utiliza para
> autocomplete (`/api/v1/database/<id>/tables/` e
> `/api/v1/database/<id>/table_metadata/`). A IA consegue assim explorar
> tabelas do banco que ainda não foram configuradas como datasets no Superset.

#### Ações de Escrita (com confirmação obrigatória)

| Tool                      | Descrição                                          |
|---------------------------|----------------------------------------------------|
| `run_sql_query`           | Executa query no SQL Lab (via API do SQL Lab)      |
| `save_sql_query`          | Salva uma query SQL no SQL Lab                     |
| `create_chart`            | Cria um novo chart                                 |
| `edit_chart`              | Edita um chart existente                           |
| `create_dashboard`        | Cria um novo dashboard                             |
| `edit_dashboard`          | Edita metadados de um dashboard                    |
| `add_chart_to_dashboard`  | Adiciona chart a um dashboard existente            |
| `create_dataset`          | Cria dataset a partir de uma query SQL             |

**Nota**: `run_sql_query` tem `requires_confirmation = True` por padrão. O admin pode relaxar isso nas configurações para roles específicos.

#### Exemplo — Tool `list_datasets`

```python
# superset/ai/tools/datasets.py

from superset.datasets.dao import DatasetDAO

class ListDatasetsTool(AITool):
    name = "list_datasets"
    description = (
        "Lista todos os datasets disponíveis no Superset que o usuário tem acesso. "
        "Retorna id, nome, tipo e database de cada dataset."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "search": {
                "type": "string",
                "description": "Filtro opcional por nome do dataset"
            }
        },
        "required": []
    }
    requires_confirmation = False

    def execute(self, user: "User", params: dict) -> ToolResult:
        try:
            datasets = DatasetDAO.find_by_user(user, search=params.get("search"))
            return ToolResult(
                success=True,
                data=[
                    {"id": d.id, "name": d.table_name, "database": d.database.database_name}
                    for d in datasets
                ]
            )
        except Exception as ex:
            return ToolResult(success=False, data=None, error=str(ex))
```

#### Exemplo — Tools `list_database_tables` e `get_table_schema`

Estas tools são essenciais para que a IA consiga explorar tabelas do banco que
**ainda não foram configuradas como datasets** no Superset — o mesmo que o SQL
Lab faz para exibir o painel de schema e oferecer autocomplete.

```python
# superset/ai/tools/databases.py

from superset.databases.dao import DatabaseDAO
from superset.databases.commands.tables import TablesDatabaseCommand
from superset.databases.commands.table_metadata import TableMetadataDatabaseCommand

class ListDatabaseTablesTool(AITool):
    name = "list_database_tables"
    description = (
        "Lista todas as tabelas disponíveis em um banco de dados conectado ao Superset. "
        "Inclui tabelas que ainda não foram configuradas como datasets. "
        "Use quando precisar explorar o que existe no banco antes de criar um dataset ou query."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "database_id": {
                "type": "integer",
                "description": "ID do banco de dados (obtido via list_databases)"
            },
            "schema": {
                "type": "string",
                "description": "Schema/namespace específico (opcional). Se omitido, retorna o schema padrão."
            },
            "search": {
                "type": "string",
                "description": "Filtro por nome da tabela (opcional)"
            }
        },
        "required": ["database_id"]
    }
    requires_confirmation = False

    def execute(self, user: "User", params: dict) -> ToolResult:
        try:
            database = DatabaseDAO.find_by_id(params["database_id"])
            if not database:
                return ToolResult(success=False, data=None, error="Database não encontrado")

            # Usa o mesmo comando interno do SQL Lab
            tables = TablesDatabaseCommand(
                database=database,
                schema_name=params.get("schema"),
                search=params.get("search"),
            ).run()

            return ToolResult(
                success=True,
                data=[
                    {"name": t.value, "schema": t.extra.get("schema")}
                    for t in tables
                ]
            )
        except Exception as ex:
            return ToolResult(success=False, data=None, error=str(ex))


class GetTableSchemaTool(AITool):
    name = "get_table_schema"
    description = (
        "Retorna as colunas e tipos de dados de uma tabela específica em um banco conectado. "
        "Funciona para qualquer tabela do banco, mesmo sem dataset configurado no Superset. "
        "Use antes de montar uma query SQL para saber os nomes exatos das colunas."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "database_id": {
                "type": "integer",
                "description": "ID do banco de dados"
            },
            "table_name": {
                "type": "string",
                "description": "Nome da tabela"
            },
            "schema": {
                "type": "string",
                "description": "Schema/namespace da tabela (opcional)"
            }
        },
        "required": ["database_id", "table_name"]
    }
    requires_confirmation = False

    def execute(self, user: "User", params: dict) -> ToolResult:
        try:
            database = DatabaseDAO.find_by_id(params["database_id"])
            if not database:
                return ToolResult(success=False, data=None, error="Database não encontrado")

            # Usa o mesmo comando interno do SQL Lab para inspecionar schema
            metadata = TableMetadataDatabaseCommand(
                database=database,
                table_name=params["table_name"],
                schema_name=params.get("schema"),
            ).run()

            return ToolResult(
                success=True,
                data={
                    "table": params["table_name"],
                    "schema": params.get("schema"),
                    "columns": [
                        {
                            "name": col["name"],
                            "type": col["type"],
                            "nullable": col.get("nullable", True),
                            "comment": col.get("comment"),
                        }
                        for col in metadata.get("columns", [])
                    ],
                    "primary_key": metadata.get("primaryKey", {}).get("columns", []),
                    "foreign_keys": metadata.get("foreignKeys", []),
                }
            )
        except Exception as ex:
            return ToolResult(success=False, data=None, error=str(ex))
```

---

## Modelo de Dados — AIAgent

```python
# superset/ai/models.py

from superset.extensions import db
from superset.models.helpers import AuditMixinNullable
import uuid

class AIAgent(AuditMixinNullable, db.Model):
    __tablename__ = "ai_agent"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(256), nullable=False)
    provider = db.Column(
        db.Enum("openai", "ollama", "deepseek", "anthropic", "codex", name="ai_provider"),
        nullable=False
    )
    model = db.Column(db.String(128), nullable=False)
    base_url = db.Column(db.String(512), nullable=True)   # Para Ollama/self-hosted
    api_key_encrypted = db.Column(db.Text, nullable=True) # Criptografado com Fernet
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    # Permissões: quais roles podem usar este agente
    # Relacionamento many-to-many com Role do Flask-AppBuilder
    allowed_roles = db.relationship("Role", secondary="ai_agent_roles")
```

### Migração

Uma migration Alembic deve ser criada para as tabelas:
- `ai_agent`
- `ai_agent_roles` (tabela de associação)

---

## Adaptadores de Provedor

### Interface Base

```python
# superset/ai/providers/base.py

from abc import ABC, abstractmethod

class AIProviderAdapter(ABC):
    """Interface unificada para todos os provedores de IA."""

    @abstractmethod
    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str,
    ) -> ProviderResponse:
        """
        Envia mensagens + tools para o provedor e retorna a resposta.
        Normaliza o formato de tool_calls para o padrão interno.
        """
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Testa se a API key / URL estão corretos."""
        ...
```

### Estratégia de Compatibilidade (DeepSeek, Codex)

DeepSeek e OpenAI Codex usam a mesma interface da API OpenAI. O `OpenAIProviderAdapter` aceita `base_url` customizado, tornando-o reutilizável para provedores compatíveis:

```python
# superset/ai/providers/openai_provider.py

class OpenAIProviderAdapter(AIProviderAdapter):
    def __init__(self, api_key: str, base_url: str | None = None):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        # base_url=None → OpenAI oficial
        # base_url="https://api.deepseek.com" → DeepSeek
        # base_url="http://localhost:11434/v1" → Ollama com API OpenAI-compatible
```

---

## System Prompt

O orquestrador monta um system prompt dinâmico com:

```
Você é um assistente de BI integrado ao Apache Superset.

Contexto atual do usuário:
- Página: {context.page}
- Recurso: {context.resource_name} (ID: {context.resource_id})

Suas capacidades:
- Consultar datasets, databases, charts e dashboards disponíveis
- Criar e editar charts e dashboards
- Executar e salvar queries SQL via SQL Lab
- Criar datasets a partir de queries

Regras importantes:
1. NUNCA acesse bancos de dados diretamente — use apenas as ferramentas disponíveis
2. Ações de criação/edição SEMPRE requerem confirmação do usuário
3. Para queries SQL, prefira consultas SELECT — evite DML/DDL
4. Responda sempre em português (ou no idioma do usuário)
5. Ao propor ações, explique o que será feito antes de solicitar confirmação
```

---

## Segurança das API Keys

As API keys dos agentes são criptografadas usando a mesma chave Fernet do Superset (`SECRET_KEY`) antes de serem armazenadas no banco. Nunca são retornadas nas respostas da API (apenas `"****"` para confirmar que estão configuradas).

```python
from cryptography.fernet import Fernet
from superset import app

def encrypt_api_key(api_key: str) -> str:
    f = Fernet(app.config["SECRET_KEY"].encode())
    return f.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted: str) -> str:
    f = Fernet(app.config["SECRET_KEY"].encode())
    return f.decrypt(encrypted.encode()).decode()
```
