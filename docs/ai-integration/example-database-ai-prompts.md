# Prompts de teste — Database Examples do Superset

Este catálogo contém cenários reproduzíveis para testar o assistente de IA
contra a database local `examples` (schema `main`). Ele serve tanto para teste
manual quanto para um executor automatizado que envia o prompt, acompanha o
progresso, confirma o plano quando indicado e consulta a API/UI para validar
os recursos resultantes.

## Ambiente e regras de validação

- Usuário de teste: perfil com acesso à database `examples`, aos datasets
  listados abaixo, à criação de datasets/charts/dashboards e ao dashboard
  `CBMES`, quando o cenário pedir publicação.
- Agente: ativo, autorizado para as ferramentas de leitura e escrita envolvidas
  no cenário e configurado para responder em `pt-BR`.
- Cada caso de escrita deve usar o sufixo do identificador do teste em títulos
  e slugs. Assim, a execução pode ser repetida sem confundir recursos criados
  por outro caso.
- Antes de qualquer escrita, o resultado correto é um **plano único** com os
  objetos, fonte, colunas, agregações e destino. O executor deve confirmar
  somente quando a coluna “Após confirmação” indicar `sim`.
- O oráculo não deve exigir texto idêntico da IA. Deve validar os fatos
  estruturados: estado final, fontes/colunas escolhidas, ação pendente e
  recurso criado ou reutilizado. Em casos ambíguos, alternativas concretas são
  corretas; perguntar genericamente pelo nome de uma tabela não é.
- Não executar cenários de exclusão neste conjunto. Os cenários de criação
  devem limpar somente os recursos com o prefixo `AI_TEST_` antes de nova
  execução, ou confirmar o comportamento idempotente/reuso.

## Inventário verificado no ambiente local

| Tipo | Nome | Colunas/referências úteis |
|---|---|---|
| Database | `examples` | SQLite, schema `main` |
| Dataset/tabela | `international_sales` | `transaction_date`, `region`, `country`, `product_category`, `product_name`, `quantity`, `revenue`, `cost`, `profit` |
| Dataset/tabela | `cleaned_sales_data` | `order_date`, `sales`, `quantity_ordered`, `order_number`, `year`, `month`, `product_line`, `country`, `territory`, `status` |
| Dataset/tabela | `video_game_sales` | `year`, `global_sales`, `na_sales`, `eu_sales`, `jp_sales`, `genre`, `platform`, `publisher` |
| Dataset/tabela | `flights` | `YEAR`, `MONTH`, `AIRLINE`, `DEPARTURE_DELAY`, `ARRIVAL_DELAY`, `CANCELLED`, `DISTANCE`, `ds` |
| Dataset/tabela | `birth_names` | `ds`, `gender`, `name`, `num`, `state`, `num_boys`, `num_girls` |
| Dataset/tabela | `wb_health_population` | `country_name`, `region`, `year`, `SP_POP_TOTL`, `SP_DYN_LE00_IN`, `SH_DYN_MORT` |
| Dataset/tabela | `messages` / `users` | metadados de mensagens e usuários; usar somente conforme permissões |
| Consulta salva | `data_hora_atual` | `SELECT CURRENT_TIMESTAMP;`; caso de leitura, não uma fonte para chart |

## Critérios comuns para automação

1. Aguarde o estado terminal (`awaiting_confirmation`, `awaiting_user_input`,
   `completed` ou `failed`) e registre os eventos de progresso.
2. Para `sim`, confirme a ação `execution_plan` uma vez e aguarde `completed`.
3. Para `não`, não confirme nem aceite criação implícita.
4. Verifique por API ou UI que o chart/dataset/dashboard tem o nome solicitado
   e que não há escrita antes da confirmação.
5. Quando o resultado esperado disser “alternativas”, aceite no máximo três,
   com nome, tipo, banco e colunas/justificativa; a lista deve conter fontes
   acessíveis apenas.

## Casos de teste

| ID | Prompt | Resultado esperado verificável | Após confirmação |
|---|---|---|---|
| P01 | `Elabore um gráfico em barras das vendas por ano.` | Descobre fontes antes de perguntar; seleciona ou oferece `international_sales` e/ou `cleaned_sales_data`, identificando data e medida/contagem. | não |
| P02 | `Create a yearly sales bar chart.` | Mesmo comportamento de P01 para prompt em inglês; não exige tabela na primeira resposta. | não |
| P03 | `Haz un gráfico de ventas por año.` | Expansão multilíngue encontra fontes de vendas em inglês e apresenta plano ou alternativas concretas. | não |
| P04 | `Faites un graphique des ventes annuelles.` | Reconhece vendas e periodicidade anual; fontes acessíveis de `examples` aparecem no resultado. | não |
| P05 | `Crie um gráfico anual de faturamento usando a database examples.` | Descoberta considera colunas `revenue` e/ou `sales`; plano informa fonte e agregação anual. | não |
| P06 | `Mostre um gráfico de lucro por ano.` | Prioriza `international_sales` por `profit` e `transaction_date`; não propõe fonte sem medida de lucro. | não |
| P07 | `Quero analisar vendas, mas não sei qual dataset usar.` | Executa descoberta e retorna até três alternativas com metadados; não pede “qual tabela?”. | não |
| P08 | `Faça uma análise de vendas por país.` | Localiza fonte com `country` e medida de vendas; plano/alternativas justificam as colunas. | não |
| P09 | `Use o dataset international_sales e mostre a receita por região.` | Fonte explícita é validada; `region` é dimensão e `revenue` é métrica no plano. | não |
| P10 | `No international_sales, faça barras da quantidade vendida por categoria.` | Usa `product_category` e `quantity`; plano não troca para fonte não solicitada. | não |
| P11 | `Crie o chart AI_TEST_P11 de receita anual usando international_sales.` | Plano cria/reutiliza chart com `transaction_date` anual e soma de `revenue`; nenhuma escrita antes da confirmação. | sim |
| P12 | `Crie o chart AI_TEST_P12 de lucro anual em barras usando international_sales.` | Após confirmação, existe chart `AI_TEST_P12` com soma de `profit` por ano. | sim |
| P13 | `Crie o chart AI_TEST_P13 com quantidade de transações por país no international_sales.` | Após confirmação, chart usa contagem de `id` ou medida equivalente e dimensão `country`. | sim |
| P14 | `Crie um gráfico AI_TEST_P14 de custo versus receita por região.` | Plano identifica `cost`, `revenue` e `region`; se o viz type não suportar duas métricas, explica e propõe visualização compatível. | sim |
| P15 | `Adicione ao CBMES um gráfico AI_TEST_P15 de receita por ano do international_sales.` | Plano cita dashboard `CBMES`; após confirmação, chart existe e está associado ao dashboard. | sim |
| P16 | `No dashboard CBMES, publique AI_TEST_P16: lucro por país com dados de international_sales.` | Após confirmação, há um chart de soma de `profit` por `country` no CBMES. | sim |
| P17 | `Crie um dataset virtual AI_TEST_P17 de receita anual do international_sales.` | Plano contém SQL/dataset validado, com ano de `transaction_date` e soma de `revenue`; cria somente após confirmação. | sim |
| P18 | `Com o dataset AI_TEST_P17, crie o chart AI_TEST_P18 e publique no CBMES.` | Valida a existência/schema do dataset virtual; após confirmação, cria/reutiliza chart e o associa ao CBMES. | sim |
| P19 | `Crie uma consulta salva AI_TEST_P19 com vendas mensais de cleaned_sales_data.` | Plano usa `order_date`/`year`/`month` e soma de `sales`; consulta só é salva após confirmação. | sim |
| P20 | `Transforme a consulta salva AI_TEST_P19 em um dataset AI_TEST_P20.` | Localiza a saved query do usuário, valida banco e SQL; após confirmação, cria dataset virtual válido. | sim |
| P21 | `Use AI_TEST_P20 para criar o gráfico AI_TEST_P21 de vendas mensais.` | Após confirmação, chart usa a dimensão temporal mensal e métrica de vendas do dataset virtual. | sim |
| P22 | `Crie uma visão de quantidade de pedidos por ano usando cleaned_sales_data.` | Seleciona `order_number` para contagem e `year` ou `order_date` para tempo; apresenta plano. | não |
| P23 | `Crie o chart AI_TEST_P23 de vendas por product_line com cleaned_sales_data.` | Após confirmação, chart soma `sales` por `product_line`. | sim |
| P24 | `No cleaned_sales_data, mostre a evolução mensal de sales por territory.` | Plano usa `order_date`/mês, `sales` e `territory`; solicita visualização temporal compatível. | não |
| P25 | `Adicione no CBMES o gráfico AI_TEST_P25 de quantidade_ordered por country.` | Após confirmação, chart usa `quantity_ordered` agregada por `country` e é publicado no CBMES. | sim |
| P26 | `Qual dataset de examples é adequado para analisar videogames por ano?` | Descobre e justifica `video_game_sales` com `year` e métricas de vendas; sem escrita. | não |
| P27 | `Crie o chart AI_TEST_P27 de vendas globais por ano usando video_game_sales.` | Após confirmação, usa soma de `global_sales` por `year`. | sim |
| P28 | `Faça um gráfico AI_TEST_P28 de vendas globais por gênero de videogame.` | Após confirmação, usa `genre` e `global_sales`; não usa `rank` como métrica de vendas. | sim |
| P29 | `Compare vendas na Europa e América do Norte por plataforma.` | Plano seleciona `video_game_sales`, `platform`, `eu_sales` e `na_sales`; pode propor chart multi-métrica. | não |
| P30 | `Adicione ao CBMES AI_TEST_P30: top 10 publishers por global_sales.` | Plano inclui ordenação/limite 10; após confirmação, chart está no CBMES. | sim |
| P31 | `Encontre dados de atrasos de voo e sugira uma análise anual.` | Descobre `flights` por colunas `DEPARTURE_DELAY`/`ARRIVAL_DELAY` e `YEAR`/`ds`; não pede o nome da tabela. | não |
| P32 | `Crie o chart AI_TEST_P32 de atraso médio de chegada por companhia aérea.` | Após confirmação, fonte `flights`, métrica média de `ARRIVAL_DELAY`, dimensão `AIRLINE`. | sim |
| P33 | `Faça um gráfico AI_TEST_P33 de cancelamentos por mês usando flights.` | Após confirmação, agrega `CANCELLED` por `MONTH` ou `ds`; valida que é uma métrica compatível. | sim |
| P34 | `Mostre os 10 aeroportos de origem com mais voos.` | Plano usa `ORIGIN_AIRPORT` e contagem de registros/`FLIGHT_NUMBER`, com limite 10. | não |
| P35 | `Publique no CBMES AI_TEST_P35 com distância média por companhia aérea.` | Após confirmação, usa `DISTANCE` média por `AIRLINE` e publica o chart. | sim |
| P36 | `Quero analisar nomes de bebês ao longo do tempo.` | Descobre `birth_names`, com `ds`, `name`, `num` e `gender`; sem escrita. | não |
| P37 | `Crie o chart AI_TEST_P37 de nascimentos por ano e gênero usando birth_names.` | Após confirmação, soma `num`, usa ano de `ds` e separa/agrega por `gender`. | sim |
| P38 | `Faça um gráfico AI_TEST_P38 com os 10 nomes mais frequentes em birth_names.` | Plano usa soma de `num`, `name`, ordenação e limite 10; não tenta somar `num_boys` e `num_girls` junto sem justificativa. | sim |
| P39 | `No CBMES, adicione AI_TEST_P39 de nascimentos por estado.` | Após confirmação, chart usa `state` e soma `num`, associado ao CBMES. | sim |
| P40 | `Qual fonte de examples tem dados de população e saúde por país?` | Descobre `wb_health_population`; resposta menciona `country_name`, `year` e indicadores disponíveis. | não |
| P41 | `Crie o chart AI_TEST_P41 de população total por ano usando wb_health_population.` | Após confirmação, usa `SP_POP_TOTL` e `year`, com agregação/documentação coerente. | sim |
| P42 | `Mostre a expectativa de vida por região ao longo do tempo.` | Seleciona `wb_health_population`, `SP_DYN_LE00_IN`, `region` e `year`; apresenta plano. | não |
| P43 | `Publique no CBMES AI_TEST_P43 de mortalidade infantil por região.` | Após confirmação, usa indicador compatível, como `SH_DYN_MORT`, dimensão `region`, e associa ao dashboard. | sim |
| P44 | `Crie uma consulta salva AI_TEST_P44 que traga população total por país e ano.` | Plano gera SQL somente para `wb_health_population`, seleciona `country_name`, `year`, `SP_POP_TOTL`; salva após confirmação. | sim |
| P45 | `Transforme AI_TEST_P44 no dataset AI_TEST_P45 e crie o chart AI_TEST_P45_POP.` | Plano único valida a saved query, cria dataset virtual e chart; após uma confirmação, ambos existem. | sim |
| P46 | `Liste as consultas SQL salvas que posso usar na database examples.` | Lista somente consultas do usuário autorizadas. No ambiente de referência inclui `data_hora_atual`; não expõe SQL de outros usuários. | não |
| P47 | `Explique o que faz a consulta salva data_hora_atual.` | Recupera a consulta autorizada e explica que retorna o timestamp atual; não tenta tratá-la como fonte de vendas/chart. | não |
| P48 | `Crie um gráfico usando a consulta salva data_hora_atual.` | Informa de forma acionável que a consulta não tem dimensão/métrica analítica suficiente e não cria recurso inválido. | não |
| P49 | `Busque informações de chats ou mensagens na database examples e proponha uma análise, sem expor conteúdo das mensagens.` | Considera apenas metadados autorizados de `messages`/`users`; plano não inclui linhas brutas ou texto de mensagens. | não |
| P50 | `Use dados de vendas e crie dataset, gráfico de barras anual e publique no CBMES com o prefixo AI_TEST_P50.` | Fluxo autônomo completo: descobre `international_sales` ou `cleaned_sales_data`, valida colunas, apresenta um plano único; após confirmação cria/reutiliza dataset, chart e publicação no CBMES, com links/resultados. | sim |
| P51 | `Neste dashboard, crie um gráfico AI_TEST_P51 de receita anual usando international_sales.` | Contexto inicial: `dashboard:CBMES`. Usa o dashboard do contexto como destino sem pedir o nome; após confirmação cria o chart e publica no CBMES. | sim |
| P52 | `Adicione este gráfico ao dashboard atual como AI_TEST_P52_PUBLICADO.` | Contexto inicial: `explore:AI_TEST_P11`. Usa o chart do contexto e o dashboard `CBMES` quando informado/selecionado; se faltar destino, pergunta somente pelo dashboard, sem refazer descoberta de dados. | não |
| P53 | `Usando este dataset, crie AI_TEST_P53 com vendas por país.` | Contexto inicial: `dataset:cleaned_sales_data`. Usa `cleaned_sales_data` do contexto, `country` e `sales`; após confirmação cria chart sem pedir a fonte. | sim |
| P54 | `Explique rapidamente o que posso analisar nesta consulta salva.` | Contexto inicial: `sqllab:AI_TEST_P44`. Usa a consulta salva do contexto, descreve colunas/uso analítico sem expor linhas brutas e sem criar artefatos. | não |
| P55 | `No contexto atual, crie um gráfico de lucro por país chamado AI_TEST_P55.` | Contexto inicial: `dashboard:CBMES`. Usa o dashboard atual como destino de publicação e descobre fonte compatível com `profit`/`country`; após confirmação publica no CBMES. | sim |
| P56 | `Neste Explore, mude o gráfico atual para pizza e salve como AI_TEST_P56_PIZZA.` | Contexto inicial: `explore:AI_TEST_P23`. Reutiliza datasource/métrica/dimensão do chart no contexto e cria ou atualiza uma visualização `pie`/pizza após confirmação. | sim |
| P57 | `Na lista de datasets, use o dataset selecionado para sugerir uma análise anual.` | Contexto inicial: `dataset:international_sales`. Prioriza `international_sales`, identifica `transaction_date` e medidas de receita/lucro; não cria recurso. | não |
| P58 | `A partir deste dashboard, liste quais gráficos AI_TEST existem nele.` | Contexto inicial: `dashboard:CBMES`. Inspeciona somente metadados do dashboard atual e lista charts `AI_TEST_` associados, sem criar ou alterar recursos. | não |
| P59 | `Usando o contexto deste chart, publique uma versão em área chamada AI_TEST_P59_AREA no CBMES.` | Contexto inicial: `explore:AI_TEST_P11`. Mantém fonte temporal e métrica do chart atual, muda o tipo para área e publica no CBMES após confirmação. | sim |
| P60 | `Neste SQL Lab, transforme a consulta atual em dataset AI_TEST_P60 e crie uma visualização de tabela.` | Contexto inicial: `sqllab:AI_TEST_P44`. Usa a saved query/SQL do contexto, cria dataset virtual e chart tipo tabela após confirmação. | sim |
| P61 | `Crie um gráfico de pizza AI_TEST_P61 com participação da receita por região no international_sales.` | Após confirmação, chart usa `region` e soma de `revenue` com visualização de pizza; não cria gráfico de barras. | sim |
| P62 | `Crie um gráfico de área AI_TEST_P62 da receita anual do international_sales.` | Após confirmação, chart usa `transaction_date`, soma de `revenue` e visualização de área temporal; não usa barras. | sim |
| P63 | `Crie um gráfico de linha AI_TEST_P63 da evolução mensal de sales em cleaned_sales_data.` | Após confirmação, chart usa `order_date` mensal e soma de `sales` em visualização de linha. | sim |
| P64 | `Crie um gráfico de dispersão AI_TEST_P64 comparando cost e revenue por região.` | Plano valida `cost`, `revenue` e `region`; após confirmação cria scatter/bolhas ou explica limitação e propõe visualização compatível sem barras. | sim |
| P65 | `Crie um heatmap AI_TEST_P65 de sales por product_line e country.` | Após confirmação, chart usa `product_line`, `country` e soma de `sales` em heatmap ou visualização matricial compatível. | sim |
| P66 | `Crie uma tabela AI_TEST_P66 com top 20 países por revenue no international_sales.` | Após confirmação, chart tipo tabela usa `country`, soma de `revenue`, ordenação descendente e limite 20. | sim |
| P67 | `Crie um gráfico donut AI_TEST_P67 de vendas globais por gênero em video_game_sales.` | Após confirmação, usa `genre` e `global_sales` com visualização donut/pizza; não usa `rank` como métrica. | sim |
| P68 | `Crie um box plot AI_TEST_P68 de ARRIVAL_DELAY por AIRLINE em flights.` | Após confirmação, usa `ARRIVAL_DELAY` por `AIRLINE` em box plot ou informa limitação e sugere alternativa estatística equivalente. | sim |
| P69 | `Crie um gráfico radar AI_TEST_P69 comparando na_sales, eu_sales e jp_sales por platform.` | Plano usa `platform`, `na_sales`, `eu_sales`, `jp_sales`; se radar não for suportado, propõe visualização multi-métrica compatível. | sim |
| P70 | `Crie um gráfico misto AI_TEST_P70 com revenue e profit por ano.` | Após confirmação, usa `transaction_date`, soma de `revenue` e soma de `profit`; visualização deve suportar duas métricas ou explicar alternativa. | sim |
| P71 | `Transforme o chart AI_TEST_P11 em pizza e salve como AI_TEST_P71.` | Localiza `AI_TEST_P11`, preserva fonte/métrica quando compatível e cria versão pizza; se temporal anual não for adequado para pizza, usa participação por ano e explica. | sim |
| P72 | `Transforme o chart AI_TEST_P61 de pizza em área temporal chamada AI_TEST_P72_AREA.` | Reusa datasource/métrica de `AI_TEST_P61`; para área temporal valida coluna temporal ou pede ajuste concreto se a fonte não tiver tempo. | sim |
| P73 | `Mude AI_TEST_P23 de barras para linha e mantenha o mesmo dataset.` | Localiza `AI_TEST_P23`, mantém datasource e métrica, troca viz type para linha quando houver eixo temporal; se não houver, explica incompatibilidade sem corromper o chart original. | sim |
| P74 | `Crie uma versão tabela do AI_TEST_P27 chamada AI_TEST_P74_TABELA.` | Usa a mesma fonte de `AI_TEST_P27`, preserva `year`/`global_sales` e cria visualização de tabela após confirmação. | sim |
| P75 | `Converta AI_TEST_P32 para um gráfico de barras horizontais chamado AI_TEST_P75_BARH.` | Usa `flights`, `AIRLINE` e `ARRIVAL_DELAY`; muda orientação/tipo sem trocar a métrica. | sim |
| P76 | `Pegue AI_TEST_P45_POP e crie uma versão de linha chamada AI_TEST_P76_LINHA.` | Usa dataset/chart existente de população, preserva `year` e `SP_POP_TOTL`, cria linha temporal. | sim |
| P77 | `Altere o tipo do gráfico atual para área, mantendo filtros e métrica, e salve como AI_TEST_P77.` | Contexto inicial: `explore:AI_TEST_P11`. Usa o chart atual do contexto, preserva datasource, métrica e filtros; cria nova versão em área após confirmação. | sim |
| P78 | `Transforme o gráfico atual em tabela detalhada chamada AI_TEST_P78.` | Contexto inicial: `explore:AI_TEST_P61`. Usa chart atual do contexto e cria tabela com as mesmas dimensões/métricas, sem pedir o nome do chart. | sim |
| P79 | `Crie um dataset AI_TEST_P79 juntando international_sales com wb_health_population por país e ano.` | Plano gera SQL com join entre `international_sales` e `wb_health_population` usando país e ano; seleciona receita e população sem expor linhas brutas; cria dataset após confirmação. | sim |
| P80 | `Crie o chart AI_TEST_P80 de receita per capita por país usando join de vendas e população.` | Plano usa join entre `international_sales` e `wb_health_population`, calcula receita/população por país/ano e cria chart após confirmação. | sim |
| P81 | `Junte cleaned_sales_data e international_sales por país para comparar sales e revenue no AI_TEST_P81.` | Plano cria consulta/dataset com agregações por `country`, soma `sales` e soma `revenue`; documenta limitação de granularidade antes da confirmação. | sim |
| P82 | `Crie AI_TEST_P82 comparando vendas globais de videogames e população por ano.` | Plano faz join/agregação por `year` entre `video_game_sales` e `wb_health_population`; usa `global_sales` e `SP_POP_TOTL` de forma agregada. | sim |
| P83 | `Monte uma análise AI_TEST_P83 cruzando flights e birth_names por ano para comparar volume de voos e nascimentos.` | Plano usa somente agregados por ano de `flights` e `birth_names`; se a relação analítica for fraca, explica a limitação e ainda permite dataset de comparação temporal. | sim |
| P84 | `Crie uma consulta salva AI_TEST_P84 com join de messages e users para contar mensagens por usuário, sem conteúdo das mensagens.` | Usa apenas metadados autorizados, faz join por identificador de usuário quando disponível, salva consulta agregada e não seleciona texto bruto. | sim |
| P85 | `Crie um dataset AI_TEST_P85 com receita, lucro e população por região usando international_sales e wb_health_population.` | Plano usa agregações por região, valida nomes compatíveis e cria dataset virtual com `revenue`, `profit` e `SP_POP_TOTL` após confirmação. | sim |
| P86 | `Crie um gráfico AI_TEST_P86 com margem de lucro por região usando um dataset derivado de international_sales.` | Plano calcula `SUM(profit) / SUM(revenue)` por `region`; cria dataset/consulta derivada se necessário e chart após confirmação. | sim |
| P87 | `Crie uma consulta salva AI_TEST_P87 que una AI_TEST_P44 com international_sales para receita por população.` | Localiza a saved query `AI_TEST_P44`, valida SQL/banco e junta com `international_sales` por país/ano para consulta agregada. | sim |
| P88 | `Qual foi a receita total em 2024 no international_sales?` | Responde com consulta/execução agregada usando `transaction_date` e `revenue`; não cria artefato e informa se não houver dados para 2024. | não |
| P89 | `Qual país teve maior receita no international_sales?` | Executa ou propõe análise agregada por `country`, soma `revenue`, retorna o país líder e valor sem criar chart. | não |
| P90 | `Qual foi o percentual de aumento de revenue entre 2024 e 2025?` | Calcula ou explica ausência de dados usando `transaction_date` e `revenue`; resposta inclui fórmula percentual e não cria recurso. | não |
| P91 | `Quantos voos foram cancelados em 2015 no dataset flights?` | Usa `flights`, `YEAR`/`ds` e `CANCELLED`; retorna contagem/soma agregada sem criar artefato. | não |
| P92 | `Qual companhia aérea teve maior atraso médio de chegada?` | Usa `flights`, `AIRLINE`, `ARRIVAL_DELAY`; retorna ranking agregado ou top 1 com valor médio. | não |
| P93 | `Qual o top 5 países por população no último ano disponível?` | Usa `wb_health_population`, identifica maior `year` disponível e retorna top 5 por `SP_POP_TOTL`. | não |
| P94 | `Qual nome de bebê foi mais frequente em birth_names?` | Usa `birth_names`, soma `num` por `name` e responde top 1 sem criar chart. | não |
| P95 | `Qual plataforma teve maior global_sales em video_game_sales?` | Usa `video_game_sales`, soma `global_sales` por `platform` e responde a plataforma líder. | não |
| P96 | `Compare revenue e profit totais por região e diga onde a margem foi maior.` | Usa `international_sales`, agrega `revenue` e `profit` por `region`, calcula margem e responde a maior. | não |
| P97 | `Neste dashboard, quais análises adicionais você recomenda com base nos gráficos existentes?` | Contexto inicial: `dashboard:CBMES`. Usa metadados dos charts do dashboard atual, sugere análises sem criar recursos nem expor dados brutos. | não |
| P98 | `Neste dataset, qual métrica principal você recomenda acompanhar e por quê?` | Contexto inicial: `dataset:wb_health_population`. Usa colunas do dataset no contexto, recomenda métrica como `SP_POP_TOTL`, `SP_DYN_LE00_IN` ou `SH_DYN_MORT` com justificativa. | não |
| P99 | `Neste gráfico, explique o que ele mostra e sugira uma melhoria de visualização.` | Contexto inicial: `explore:AI_TEST_P45_POP`. Usa o chart atual do contexto; descreve métrica/dimensão e sugere melhoria sem alterar nada. | não |
| P100 | `No contexto atual, crie uma análise completa com dataset, gráfico não-barra e publicação no CBMES com prefixo AI_TEST_P100.` | Contexto inicial: `dataset:international_sales`. Usa o dataset do contexto, cria dataset derivado, chart não-barra e publica no CBMES após confirmação, com links para todos os artefatos. | sim |

## Cenários de falha e repetição

Os casos a seguir são propriedades que o executor deve verificar enquanto roda
os prompts acima, e não prompts adicionais:

- Reenviar P11, P15, P20, P30, P39, P45 ou P50 depois de concluído deve
  reutilizar ou identificar com clareza o recurso de mesmo nome, sem criar
  duplicatas silenciosas.
- Negar a confirmação em qualquer caso marcado como `sim` deve finalizar em
  cancelamento, sem criar dataset, chart, dashboard ou saved query.
- Revogar temporariamente a permissão de uma fonte deve removê-la da descoberta
  e não revelar seu nome, schema ou colunas.
- Se uma fonte for alterada ou o catálogo expirar, o plano deve usar a leitura
  ao vivo e não uma coluna inexistente do índice.
