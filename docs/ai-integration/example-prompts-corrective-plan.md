# Plano corretivo — Suíte de prompts da database Examples

## Origem e objetivo

Este plano responde à execução real dos 50 casos de
[`example-database-ai-prompts.md`](example-database-ai-prompts.md). A suíte
encontrou 24 tarefas em `awaiting_user_input`, 5 em
`awaiting_confirmation`, 20 concluídas e 1 falha explícita. Uma conclusão da
tarefa não é tratada como sucesso funcional: vários charts concluídos possuem
fonte, nome ou métrica incorretos.

O objetivo é fazer com que um pedido genérico ou com fonte explícita gere um
plano correto, uma única confirmação e, após a execução, recursos utilizáveis
no Superset — especialmente charts que carreguem dados sem erro.

## Problemas confirmados

| Prioridade | Problema | Evidência |
|---|---|---|
| P0 | Charts criados não carregam: `Data error: Metric 'SUM(na_sales)' does not exist`. | P01 gerou especificação com a string `SUM(na_sales)`; charts criados apresentam o mesmo padrão de erro. |
| P0 | A fonte explicitamente indicada não é selecionada. | P09 e diversos cenários com `international_sales`, `cleaned_sales_data`, `flights` e `birth_names` retornaram alternativas. |
| P0 | O ranking seleciona fontes semanticamente erradas. | P01–P03 escolheram `video_game_sales`/`na_sales` para vendas transacionais anuais. |
| P1 | Extração de intenção usa palavras de parada como tema. | Descobertas por `de`, `a`, `das`, `tempo`, `origem` e `anual`. |
| P1 | O plano ignora título/slug/destino pedidos. | Recursos `AI_TEST_*` foram criados como `Vendas`, `Flights` etc.; só um chart foi associado ao `cbmes`. |
| P1 | Fluxos encadeados não preservam dependências. | P17→P18 e P19→P20→P21 falharam quando o primeiro recurso não foi criado. |
| P2 | Respostas dependentes do Ollama são lentas ou desviam para texto em vez de ferramenta. | Casos multilíngues e de saved query levaram dezenas de segundos ou responderam sem executar a ação. |

## Ordem de trabalho

### 8.1 Bloqueio de charts inválidos (P0)

1. Rastrear a transformação `ChartSpecification` → payload de criação de
   chart → `query_context`/`form_data` usado pelo Superset.
2. Substituir métricas textuais como `SUM(na_sales)` por uma representação
   válida para a versão do Superset: métrica adhoc estruturada ou métrica
   simples existente no datasource, conforme o viz type.
3. Validar antes da confirmação que cada métrica referencia uma coluna do
   schema relido e que a agregação é permitida para o tipo da coluna.
4. Após criar/reutilizar um chart, executar uma validação de consulta/render
   sem expor linhas ao chat. Se houver erro de métrica, marcar a etapa como
   falha, não publicar no dashboard e retornar mensagem acionável.
5. Criar testes unitários por viz type e teste de integração que reproduza
   `Metric 'SUM(na_sales)' does not exist` e garanta sua ausência.

**Aceite:** cada chart da suíte abre pela URL retornada, consulta dados com
sucesso e não apresenta `Data error` nem erro de métrica no console/API.

### 8.2 Intenção, termos úteis e fonte explícita (P0)

1. Separar `source_hint` do tema analítico no parser; o nome explícito de
   dataset/tabela/saved query deve ser resolvido primeiro, por correspondência
   normalizada exata, antes de qualquer ranking temático.
2. Remover stopwords multilíngues (`a`, `de`, `das`, `por`, `the`, `by`, `des`,
   etc.) da extração de tema e rejeitar temas vazios.
3. Quando a fonte explícita existir e estiver autorizada, revalidar seu schema
   ao vivo e continuar o plano; só pedir escolha se a referência for ambígua ou
   inacessível.
4. Acrescentar pesos negativos para fontes incompatíveis com a intenção e
   pesos positivos para colunas que correspondam à medida solicitada
   (`revenue`, `profit`, `quantity`, `sales`) e ao tempo.

**Aceite:** P09, P10, P11–P18, P22–P25, P27–P28, P32–P33 e P37–P45 não pedem
nova escolha quando a fonte do prompt é acessível e inequívoca.

### 8.3 Ranking e desambiguação confiáveis (P0)

1. Criar perfis de intenção para vendas transacionais, jogos, voos,
   nascimentos e saúde; usar nomes de coluna e compatibilidade estrutural,
   não apenas termos expandidos.
2. Rever o cálculo de score para que `international_sales` e
   `cleaned_sales_data` superem `video_game_sales` em pedidos de “vendas” sem
   contexto de jogos.
3. Somente apresentar alternativas quando a margem de confiança for realmente
   insuficiente. As alternativas devem ser pertinentes e não incluir fontes
   genéricas apenas por terem colunas numéricas.
4. Registrar no plano os sinais e a pontuação vencedora para diagnóstico.

**Aceite:** P01–P08 em pt-BR/en-US/es-ES/fr-FR selecionam fonte adequada ou
apresentam no máximo três alternativas pertinentes; nunca usam
`birth_france_by_region` como sugestão para vendas, voos ou nomes de bebês.

### 8.4 Preservação de contrato e execução idempotente (P1)

1. Tornar `AI_TEST_*`, título, slug e dashboard de destino campos imutáveis do
   `AIExecutionPlan`; o planejador não pode substituí-los por títulos
   genéricos.
2. Resolver `CBMES` por nome/slug de forma case-insensitive e falhar de modo
   explícito se houver mais de um resultado, sem escolher o primeiro.
3. Antes de criar, procurar recurso do mesmo nome e datasource; reutilizar
   somente se a especificação for compatível, caso contrário informar conflito.
4. Encadear IDs reais retornados de dataset → chart → dashboard e interromper
   o plano se uma dependência falhar.

**Aceite:** P11–P45 criam/reutilizam os recursos solicitados com os nomes
exatos; P50 cria dataset, chart e publicação no CBMES em uma única confirmação.

### 8.5 Saved queries, respostas de ferramenta e segurança (P1)

1. Tratar `data_hora_atual` como consulta escalar não analítica e responder sem
   iniciar descoberta de datasets; impedir chart/dataset inválido dela.
2. Garantir que `list_saved_queries` habilite e use `get_saved_query` quando o
   usuário citar uma consulta pelo nome.
3. Para criação de saved query, validar SQL, schema de resultado e banco antes
   de montar o plano; persistir somente após aprovação.

**Aceite:** P46 e P47 respondem corretamente; P48 recusa a criação com motivo
claro; P19→P20→P21 e P44→P45 funcionam quando aprovados.

### 8.6 Regressão, observabilidade e desempenho (P2)

1. Converter os 50 prompts em teste parametrizado de integração, com oráculos
   estruturados de fonte, colunas, plano, recursos e renderização do chart.
2. Executar uma etapa de smoke test para cada chart criado: API de dados,
   configuração do chart e carregamento via Playwright/Chromium, capturando
   `Data error` e erros de console.
3. Registrar por prompt: fonte escolhida, score, tempo de descoberta, tempo do
   Ollama, chamadas de ferramenta, estado terminal e erro seguro.
4. Definir timeout de leitura do provedor e fallback determinístico para que
   uma resposta lenta não bloqueie a suíte nem o chat.
5. Reexecutar a suíte limpa após cada subtarefa e publicar matriz
   sucesso/falha por ID.

**Aceite:** 50/50 prompts atingem seus oráculos; nenhuma criação deixa chart
inutilizável; tarefas não ficam indefinidamente em processamento.
