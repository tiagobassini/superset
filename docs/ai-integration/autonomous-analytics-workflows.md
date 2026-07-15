# Especificação — Workflows Analíticos Autônomos com Progresso

## Objetivo

Permitir que o assistente conclua pedidos analíticos compostos sem exigir que a
pessoa usuária conduza cada chamada de ferramenta. O assistente deve descobrir
fontes acessíveis, analisar metadados e resultados agregados limitados, propor
um plano, executar leituras autonomamente e solicitar uma confirmação única
antes de qualquer conjunto de alterações no Superset.

Exemplo de pedido:

> Analise o banco `international_sales`, crie um gráfico com a quantidade de
> vendas por ano e adicione-o ao dashboard `CBMES`.

## Princípios

- O modelo interpreta intenção e produz narrativa; o backend determina a ordem,
  valida recursos e executa o plano.
- Descobertas e análises de leitura são automáticas, mas continuam sujeitas a
  RBAC, RLS e permissões de datasource do usuário.
- Dataset, chart, dashboard e associações só são alterados após confirmação
  explícita do usuário.
- Um plano confirmado é imutável. Falha em uma etapa interrompe as posteriores.
- Eventos de progresso nunca incluem credenciais, SQL sensível, dados brutos ou
  conteúdo privado de outros usuários.

## Entendimento do pedido

O planejador deve produzir uma intenção tipada, em vez de depender somente de
palavras-chave para escolher ferramentas:

```json
{
  "goal": "create_chart_and_add_to_dashboard",
  "topic": "vendas internacionais",
  "source_hint": "international_sales",
  "metric": "count",
  "time_grain": "year",
  "target_dashboard": "CBMES"
}
```

Verbos como `adicionar`, `adicione`, `incluir`, `colocar no` e `publicar`
indicam uma etapa de dashboard mesmo quando a palavra “dashboard” não estiver
presente. Se um nome puder identificar mais de um tipo de recurso, o planejador
faz busca por todos os tipos e pede esclarecimento somente se não puder decidir
com segurança pelo objetivo solicitado.

## Exemplos de prompts e comportamento esperado

Os exemplos abaixo representam pedidos naturais em pt-BR. O assistente deve
interpretar a intenção, executar leituras e análises automaticamente e só pedir
confirmação antes de criar, editar, salvar ou publicar recursos.

| Pedido da pessoa usuária | Intenção e plano esperado |
|---|---|
| “Quais dados de vendas temos disponíveis?” | Descobrir bancos, datasets e tabelas com maior aderência a vendas; exibir fontes acessíveis e resumo de colunas, sem criar recursos. |
| “Analise os dados disponíveis e me diga quais gráficos seriam mais úteis.” | Perfilar fontes candidatas, identificar medidas/dimensões/tempo e retornar recomendações justificadas; perguntar qual recomendação publicar se houver mais de uma. |
| “Faça uma consulta com as vendas por ano da base international_sales.” | Localizar banco/tabela, validar colunas e montar SQL via SQL Lab; pedir confirmação antes de executar ou salvar a consulta. |
| “Crie uma saved query de faturamento mensal.” | Descobrir fonte e colunas, propor SQL e nome da consulta; confirmar uma única vez antes de salvar. |
| “Transforme a consulta ‘Vendas por mês’ em um dataset.” | Localizar a saved query do usuário, validar banco e SQL, propor nome do dataset virtual e pedir confirmação antes de criá-lo. |
| “Crie um dataset da tabela orders do banco sales.” | Localizar exatamente o banco e a tabela, inspecionar schema, validar acesso e existência; confirmar antes de criar o dataset físico. |
| “Quero um gráfico de quantidade de pedidos por ano.” | Buscar dataset/fonte apropriada, identificar coluna temporal e identificador de pedido, perfilar agregação e propor especificação de chart; confirmar antes da criação. |
| “Monte um gráfico de receita mensal usando o dataset Vendas Internacionais.” | Localizar dataset pelo nome, confirmar que há data e medida monetária, gerar configuração adequada e pedir confirmação de criação. |
| “Adicione o gráfico Vendas por Ano ao painel Executivo.” | Localizar de forma exata o chart e o dashboard, validar acesso e associação existente; pedir confirmação antes de associar. |
| “Crie um dashboard de desempenho comercial.” | Descobrir datasets relacionados, sugerir layout e conjunto de gráficos; apresentar plano completo e confirmar antes de criar o dashboard e seus charts. |
| “Analise a base international_sales e adicione ao dashboard CBMES um gráfico de quantidade de vendas por ano.” | Interpretar `international_sales` como fonte e `CBMES` como destino de dashboard pelo verbo “adicionar”; descobrir tabelas, analisar schema/agregação, criar ou localizar dataset, gerar chart e associá-lo ao dashboard após confirmação única. |
| “Preciso de uma visão executiva das vendas: encontre os dados certos, crie os principais gráficos e publique em um dashboard novo.” | Executar descoberta e perfil de dados, recomendar métricas e visualizações, criar plano com dataset(s), charts e dashboard; aguardar confirmação única e executar em sequência. |
| “Mostre a evolução de vendas, os 10 produtos mais vendidos e a distribuição por país no painel Comercial.” | Identificar uma fonte comum ou fontes compatíveis, montar três especificações de chart e localizar o dashboard; apresentar prévia e confirmar o conjunto de alterações. |
| “Use os dados que você encontrar e crie um painel útil para acompanhar o negócio.” | Fazer análise exploratória limitada, explicar quais fontes foram selecionadas e por quê, propor métricas e gráficos; nunca criar recursos sem uma confirmação explícita do plano. |

### Regras observáveis nos exemplos

- “Base”, “banco”, “tabela”, “dataset”, “consulta”, “gráfico”, “painel” e
  “dashboard” são pistas, não garantias: o planejador verifica o tipo de
  recurso por busca e contexto antes de agir.
- Quando o pedido nomeia um recurso, a busca deve ser exata ou apresentar
  candidatos; o assistente não pode escolher o primeiro resultado silenciosamente.
- Pedidos genéricos devem gerar uma proposta explicada, não recursos criados por
  suposição. A confirmação cobre todos os efeitos de escrita da proposta.
- Se faltarem dados essenciais — por exemplo, não existir coluna temporal para
  “por ano” — o fluxo entra em `awaiting_user_input` com alternativas concretas.

## Descoberta e análise

O backend executa autonomamente as etapas de leitura abaixo:

1. Localizar bancos, datasets, tabelas e dashboards candidatos por nome e tema.
2. Inspecionar schemas das fontes candidatas.
3. Pontuar fontes por similaridade de nomes e compatibilidade de tipos:
   datas, anos, medidas, identificadores e dimensões.
4. Executar um perfil agregado e limitado quando necessário: contagem de linhas,
   intervalo de datas, cardinalidade e agregações pequenas.
5. Selecionar a melhor fonte e justificar a escolha ao usuário.

Uma nova ferramenta de leitura (`profile_dataset`/`analyze_table`) deve aceitar
limites rígidos e retornar somente estatísticas agregadas. Ela não pode contornar
SQL Lab, RLS ou permissões de banco.

## Plano de execução

O `AnalyticsTaskPlanner` cria um `AIExecutionPlan` com etapas ordenadas,
parâmetros validados, estado e mensagem pública. Para o exemplo acima:

```text
localizar international_sales
→ listar tabelas e inspecionar schema
→ analisar colunas de venda e tempo
→ criar/localizar dataset válido
→ gerar especificação de chart
→ localizar dashboard CBMES
→ solicitar confirmação única
→ criar dataset/chart e associar ao dashboard
→ apresentar links e resumo analítico
```

A especificação intermediária do gráfico deve ser tipada, por exemplo:

```json
{
  "chart_title": "Quantidade de vendas por ano",
  "dataset_id": 17,
  "viz_type": "echarts_timeseries_line",
  "time_column": "order_date",
  "metric": "COUNT(sale_id)",
  "time_grain": "P1Y"
}
```

Um adaptador do backend transforma essa estrutura em `params` compatíveis com o
Superset. Nenhuma confirmação deve ser apresentada se faltarem datasource,
coluna temporal, medida, configuração JSON válida ou dashboard de destino.

## Estados e atualizações no chat

Estados da tarefa:

- `planning`: interpretação e criação do plano;
- `discovering`: busca de recursos e schemas;
- `analyzing`: perfil estatístico e escolha de fonte;
- `awaiting_confirmation`: plano de escrita disponível para aprovação;
- `executing`: etapas confirmadas em execução;
- `awaiting_user_input`: esclarecimento indispensável;
- `completed`: todas as etapas concluídas;
- `failed`: execução interrompida com motivo seguro.

Enquanto houver estado `planning`, `discovering`, `analyzing` ou `executing`, o
frontend mantém uma única mensagem de progresso atualizável e a animação de
loading. A animação só é removida em `awaiting_confirmation`,
`awaiting_user_input`, `completed` ou `failed`.

Exemplos de mensagens públicas:

```text
Procurando fontes relacionadas a “vendas internacionais”
Encontradas 3 tabelas candidatas; inspecionando colunas
Preparando gráfico “Quantidade de vendas por ano”
Aguardando confirmação para criar e publicar os recursos
Criando gráfico e adicionando ao dashboard CBMES
```

Ao terminar, a mensagem de progresso é substituída por resumo, recursos criados,
links e achados analíticos. Não deve criar diversas bolhas de chat para cada
etapa.

## Contrato de transporte

Usar Server-Sent Events (SSE) para atualizações unidirecionais, com polling
curto como fallback quando SSE não for suportado:

```text
POST /api/v1/ai/tasks
GET  /api/v1/ai/tasks/<task_id>/events
GET  /api/v1/ai/tasks/<task_id>
POST /api/v1/ai/tasks/<task_id>/confirm
POST /api/v1/ai/tasks/<task_id>/cancel
```

Eventos possuem `task_id`, `sequence`, `state`, `message`, `step` e dados
seguros para exibição. A persistência deve permitir reconectar após recarregar a
página e rejeitar tarefas pertencentes a outro usuário ou agente.

## Segurança, auditoria e falhas

- Revalidar permissões no planejamento e imediatamente antes de cada escrita.
- Aplicar expiração a planos pendentes e impedir execução duplicada.
- Auditar criação, confirmação, cancelamento, conclusão, falha e bloqueio por
  autorização sem registrar conteúdo de chat, chaves ou SQL sensível.
- Sanitizar nomes, metadados e mensagens recebidas de ferramentas antes de
  enviar ao provedor ou ao frontend.
- Exibir falhas por etapa e preservar os recursos criados até a falha; não fazer
  rollback destrutivo automático.

## Estratégia de testes

- Unitários para intenção, ambiguidade, pontuação de fontes e transições de
  estado.
- Integração para SSE/polling, expiração, reconexão, autorização e confirmação.
- E2E para o fluxo banco → dataset → chart → dashboard, progresso incremental,
  cancelamento e erro intermediário.
