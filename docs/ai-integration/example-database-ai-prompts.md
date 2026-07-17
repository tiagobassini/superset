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

## P101-P130: Dashboard Creation Tests

| ID | Prompt | Resultado esperado verificável | Após confirmação |
|---|---|---|---|
| P101 | `Crie um novo dashboard chamado AI_TEST_P101 para análise de vendas.` | Plano cria dashboard com título "AI_TEST_P101" e descrição; após confirmação dashboard existe no sistema. | sim |
| P102 | `Crie um dashboard AI_TEST_P102 com layout de 2 colunas para análises comparativas.` | Plano específica estrutura do dashboard; após confirmação dashboard está pronto para receber charts. | sim |
| P103 | `Faça um dashboard AI_TEST_P103 dedicado à análise de dados de população global.` | Plano descreve dados de `wb_health_population`; após confirmação dashboard é criado com contexto apropriado. | sim |
| P104 | `Crie um painel AI_TEST_P104 de monitoramento de vendas por região.` | Plano refere-se ao dashboard com estrutura apropriada; após confirmação dashboard existe e está vazio. | sim |
| P105 | `Monte um dashboard AI_TEST_P105 com indicadores-chave de desempenho (KPI) de videogames.` | Plano descreve KPIs da fonte `video_game_sales`; após confirmação dashboard está criado. | sim |
| P106 | `Crie um dashboard AI_TEST_P106 para análise de dados de voos.` | Plano cria dashboard referenciando `flights`; após confirmação existe no sistema. | sim |
| P107 | `Faça um dashboard AI_TEST_P107 compartilhável para stakeholders de vendas.` | Plano descreve dashboard preparado para compartilhamento; após confirmação dashboard existe. | sim |
| P108 | `Crie um dashboard AI_TEST_P108 com guia de uso para novos usuários.` | Plano inclui descrição/instruções do dashboard; após confirmação dashboard é criado. | sim |
| P109 | `Montue um dashboard AI_TEST_P109 que integre dados de múltiplas fontes de vendas.` | Plano descreve integração de `international_sales` e `cleaned_sales_data`; após confirmação dashboard existe. | sim |
| P110 | `Crie um dashboard AI_TEST_P110 com tema escuro otimizado para apresentações.` | Plano refere-se à criar dashboard; após confirmação existe no sistema e está pronto para customização. | sim |
| P111 | `Faça um dashboard AI_TEST_P111 para comparação de tendências anuais.` | Plano descreve análise temporal; após confirmação dashboard é criado. | sim |
| P112 | `Crie um painel AI_TEST_P112 interativo de análise geográfica de vendas.` | Plano refere-se a dados geográficos; após confirmação dashboard sendo criado. | sim |
| P113 | `Crie um dashboard AI_TEST_P113 com filtros globais para análise por período.` | Plano descreve filtros temporais; após confirmação dashboard existe com estrutura pronta. | sim |
| P114 | `Faça um dashboard AI_TEST_P114 focado em rentabilidade e margem de lucro.` | Plano refere-se a métricas de lucro/profitabilidade; após confirmação dashboard é criado. | sim |
| P115 | `Crie um dashboard AI_TEST_P115 com exportação de dados para relatórios.` | Plano descreve dashboard pronto para análises exportáveis; após confirmação dashboard existe. | sim |
| P116 | `Monte um dashboard AI_TEST_P116 para monitoramento em tempo real de KPIs.` | Plano descreve dashboard com refresh automático; após confirmação dashboard é criado. | sim |
| P117 | `Crie um painel AI_TEST_P117 separado por categorias de produtos.` | Plano refere-se a segmentação por `product_category`; após confirmação dashboard existe. | sim |
| P118 | `Faça um dashboard AI_TEST_P118 para análise comparativa entre regiões.` | Plano descreve estrutura regional; após confirmação dashboard é criado. | sim |
| P119 | `Crie um dashboard AI_TEST_P119 com análise de sazonalidade de vendas.` | Plano refere-se a padrões temporais; após confirmação dashboard existe. | sim |
| P120 | `Crie um painel AI_TEST_P120 dedicado à análise de dados demográficos.` | Plano cria dashboard para dados de população; após confirmação dashboard é criado com contexto apropriado. | sim |
| P121 | `Faça um dashboard AI_TEST_P121 com comparação de performance entre produtos.` | Plano refere-se a análise por produto; após confirmação dashboard é criado. | sim |
| P122 | `Crie um dashboard AI_TEST_P122 com alertas visuais para anomalias de vendas.` | Plano descreve dashboard preparado para alertas; após confirmação dashboard existe. | sim |
| P123 | `Monte um painel AI_TEST_P123 para análise de satisfação de clientes.` | Plano refere-se a dados de clientes; após confirmação dashboard é criado. | sim |
| P124 | `Crie um dashboard AI_TEST_P124 com histórico de dados para auditoria.` | Plano descreve dashboard com rastreabilidade; após confirmação dashboard existe. | sim |
| P125 | `Faça um dashboard AI_TEST_P125 para análise de custos versus receitas.` | Plano refere-se a análise de cost/revenue; após confirmação dashboard é criado. | sim |
| P126 | `Crie um painel AI_TEST_P126 com drill-down para análises granulares.` | Plano descreve interatividade do dashboard; após confirmação dashboard existe. | sim |
| P127 | `Crie um dashboard AI_TEST_P127 para gestão de dados de saúde populacional.` | Plano refere-se a `wb_health_population`; após confirmação dashboard é criado. | sim |
| P128 | `Faça um dashboard AI_TEST_P128 com sincronização entre múltiplos gráficos.` | Plano descreve interatividade; após confirmação dashboard é criado. | sim |
| P129 | `Crie um painel AI_TEST_P129 para análise de distribuição de vendas por país.` | Plano refere-se a dimensão geográfica; após confirmação dashboard é criado. | sim |
| P130 | `Crie um dashboard AI_TEST_P130 com histórico de modificações e versioning.` | Plano descreve rastreabilidade de mudanças; após confirmação dashboard é criado. | sim |

## P131-P200: Theme/Topic Search Tests

| ID | Prompt | Resultado esperado verificável | Após confirmação |
|---|---|---|---|
| P131 | `Verifique se existe um campo de "marca" ou "brand" nas fontes de dados do examples.` | Busca por variações como brand, manufacturer, marca; se não encontrar, relata ausência com sugestões de colunas similares. | não |
| P132 | `Procure dados relacionados a "renda" ou "income" em qualquer fonte de examples.` | Descobre ou nega interesse em `income` ou similares; sem criação de artefatos. | não |
| P133 | `Existe alguma fonte que contenha informações de "clientes" ou "customers"?` | Busca em metadados por tabelas/colunas relacionadas; responde com nomes e schema ou confirma ausência. | não |
| P134 | `Tem algum dataset com dados históricos de "temperaturas" ou "climáticos"?` | Busca tabulações climáticas; se não encontrar, confirma ausência sem propor criação. | não |
| P135 | `Procure por fontes com informações de "timestamps" e construa uma timeline.` | Identifica colunas temporais (`ds`, `transaction_date`, `order_date`); descreve granularidade sem criar. | não |
| P136 | `Existe na database um campo de "status" que eu possa usar para filtrar pedidos?` | Encontra `status` em `cleaned_sales_data`; descreve valores possíveis e uso analítico. | não |
| P137 | `Verifique se há dados de "cancelamentos" em qualquer dataset.` | Encontra `CANCELLED` em `flights` ou nega, descrevendo alternativas de dados disponíveis. | não |
| P138 | `Procure por qualquer coluna que represente "lucro" ou "profit" nas fontes.` | Identifica `profit` em `international_sales`; confirma com tipo de dado e agregação possível. | não |
| P139 | `Tem alguma fonte com dados de "participação de mercado" ou "market share"?` | Busca conceituais relacionados; se não direto, sugere como calcular a partir de vendas. | não |
| P140 | `Existe um field de "descrição de produto" ou "product_name" em alguma tabela?` | Encontra `product_name` e `product_category` em `international_sales` e `cleaned_sales_data`. | não |
| P141 | `Procure dados relacionados a "demanda" ou campos de "quantidade" para análise.` | Identifica `quantity`, `quantity_ordered` para demanda; descreve em que tabelas estão. | não |
| P142 | `Verifique se existe um metadado chamado "ano" ou "year" para análises temporais.` | Encontra `year` em várias tabelas; descreve granularidade temporal disponível. | não |
| P143 | `Tem algum dataset com informações de "atraso" ou "delay" de operações?` | Encontra `DEPARTURE_DELAY` e `ARRIVAL_DELAY` em `flights`; confirma disponibilidade. | não |
| P144 | `Procure por campos de "percentual", "ratio" ou "índice" nas fontes.` | Busca e relata colunas de índices ou valores percentuais; oferece alternativas para cálculo. | não |
| P145 | `Existe informação de "gênero" ou "gender" em alguma fonte para análise demográfica?` | Encontra `gender` em `birth_names`; confirma e descreve segmentação possível. | não |
| P146 | `Verifique se há campos numéricos que possam ser usados para análise estatística.` | Identifica todos os campos contínuos (revenue, sales, DISTANCE, num, etc); lista por tabela. | não |
| P147 | `Procure por fontes que tenham dados de "popularidade" ou "rankings".` | Busca colunas indicadoras de rank/popularidade; relata colunas de ordenação encontradas. | não |
| P148 | `Tem alguma fonte relacionada a "educação" ou "escolaridade"?` | Busca campos educacionais; se ausentes, confirma com alternativas demográficas. | não |
| P149 | `Existe dado de "localização" ou "endereço" em alguma tabela?` | Busca por geography/location; encontra `country`, `region`, `state`, `territory` e descreve. | não |
| P150 | `Procure por qualquer coluna que indique "crescimento" ou "trend" nas vendas.` | Identifica colunas temporais para calcular trend; oferece estrutura sem criar. | não |
| P151 | `Verifique se há uma coluna de "custo unitário" ou "unit_cost" nas fontes.` | Busca variações de custo; confirma `cost` em `international_sales` e oferece alternativas. | não |
| P152 | `Tem algum dataset com informações de "competidores" ou "competitors"?` | Busca dados competitivos; relata disponibilidade ou ausência com sugestões. | não |
| P153 | `Procure por campos de "ID" ou identificadores únicos em cada tabela.` | Identifica campos chave primária/ID em todas as tabelas; descreve estrutura. | não |
| P154 | `Existe informação de "fornecedor" ou "supplier" em alguma fonte?` | Busca dados de supply chain; se não encontrar, sugere aproximações análiticas. | não |
| P155 | `Verifique se há dados de "performance de vendedor" ou "sales_person".` | Busca campos de performance individual/por categoria; confirma com dados disponíveis. | não |
| P156 | `Procure por campos de "volume" ou "quantidade total" para benchmarking.` | Identifica colunas de volume en todas as tabelas; descreve granularidade. | não |
| P157 | `Tem alguma fonte com informações de "horário" ou "time" para análise intra-dia?` | Busca granularidade de tempo; relata nível mais fino disponível (hora/dia/mês). | não |
| P158 | `Existe um campo que represente "valor médio" ou "average_value" em alguma tabela?` | Busca campos pré-calculados; oferece como calculá-los se não encontrar. | não |
| P159 | `Procure por qualquer dado relacionado a "satisfação" ou "satisfaction_score".` | Busca métricas de satisfação; confirma ausência e oferece proxies de engajamento. | não |
| P160 | `Verifique se há informação de "período" ou "season" para análise sazonal.` | Busca variáveis sazonais; encontra `month`, `quarter` potencial; sem criar. | não |
| P161 | `Procure por campos relacionados a "endereço" ou "localização geografica" nas tabelas.` | Busca colunas de geolocalização além de `country`/`region`; relata disponibilidade. | não |
| P162 | `Existe alguma coluna com "ID" ou identificador de cliente/transação em alguma fonte?` | Busca e lista identificadores chave em cada tabela sem criar. | não |
| P163 | `Procure dados de "transporte" ou "logística" nas bases disponiveis.` | Busca tabelas ou colunas relacionadas; confirma disponibilidade. | não |
| P164 | `Verifique se há campo de "moeda" ou "currency" em alguma fonte de vendas.` | Busca e relata presença ou ausência de informação de moeda. | não |
| P165 | `Tem alguma coluna que indique "peso" ou "capacidade" de produtos?` | Busca variáveis físicas de produtos; relata sem criar. | não |
| P166 | `Procure por dados de "desconto" ou "promotion" em vendas.` | Busca campos promocionais; relata estrutura sem criar gráfico. | não |
| P167 | `Existe campo de "margem bruta" ou "gross_margin" em alguma tabela?` | Busca métricas pré-calculadas de margem ou oferece como calcular. | não |
| P168 | `Verifique se há dados de "lote" ou "batch" em transações.` | Busca informação de agrupamento de vendas; relata sem criar. | não |
| P169 | `Procure por colunas que representem "versão" ou "versioning" de dados.` | Busca campos de versionamento; relata estrutura. | não |
| P170 | `Tem alguma fonte com dados de "conformidade" ou "compliance"?` | Busca dados regulatórios; confirma disponibilidade e uso. | não |
| P171 | `Existe informação de "turno" ou "shift" em operações/vendas?` | Busca granularidade temporal além de data/hora; relata. | não |
| P172 | `Procure por dados de "qualidade" ou "quality_score" em produtos.` | Busca métricas de qualidade; relata disponibilidade. | não |
| P173 | `Verifique se há campo de "sku" ou "product_code" nas tabelas de produtos.` | Busca identificadores de produtos padrão; relata. | não |
| P174 | `Tem alguma coluna com "duração" ou "duration" de eventos/transações?` | Busca campos temporais de duração; relata granularidade. | não |
| P175 | `Procure por dados de "risco" ou "risk_level" em qualquer fonte.` | Busca campos de classificação de risco; relata. | não |
| P176 | `Existe informação de "proprietário" ou "owner" de recursos/vendas?` | Busca campos de responsabilidade/atribuição; relata. | não |
| P177 | `Verifique se há dados de "auditoria" ou "audit_trail" no sistema.` | Busca registros de rastreabilidade; confirma sem criar. | não |
| P178 | `Procure por campos de "tipo de pagamento" ou "payment_method" em transações.` | Busca segmentação de pagamento; relata. | não |
| P179 | `Tem alguma fonte com informações de "retorno" ou "return_rate"?` | Busca dados de devoluções; relata disponibilidade. | não |
| P180 | `Existe campo de "percentil" ou "percentile_rank" em alguma tabela?` | Busca campos pré-calculados de ranking; relata. | não |
| P181 | `Procure por dados de "benchmark" ou "baseline" em métricas.` | Busca referências de comparação; relata. | não |
| P182 | `Verifique se há coluna de "flag" ou "indicator" booleano em alguma fonte.` | Busca sinalizadores; relata nomes e uso. | não |
| P183 | `Tem alguma informação de "limite" ou "threshold" de vendas/operações?` | Busca campos de limites; relata. | não |
| P184 | `Existe dado de "simulação" ou "forecast" em alguma tabela?` | Busca dados preditivos ou de scenario planning; relata. | não |
| P185 | `Procure por colunas com "percentagem" ou dados já calculados em %.` | Busca campos pré-percentualizados; lista sem criar. | não |
| P186 | `Verifique se há informação de "aprovação" ou "approval_status" em transações.` | Busca fluxo de aprovação; relata. | não |
| P187 | `Tem alguma fonte com dados de "velocidade" ou "throughput"?` | Busca métricas de performance/velocidade; relata. | não |
| P188 | `Existe coluna de "precedência" ou "priority" em alguma tabela?` | Busca campos de ordenação/prioridade; relata. | não |
| P189 | `Procure por dados de "interpolação" ou "imputation" em séries temporais.` | Busca qualidade de dados temporais; relata. | não |
| P190 | `Verifique se há "tags" ou "labels" customizáveis em registros.` | Busca campos de meta-informação; relata. | não |
| P191 | `Tem alguma informação de "configuração" ou "settings" por usuário/conta?` | Busca campos de personalização; relata. | não |
| P192 | `Existe dado de "performance_score" ou métrica similar em alguma tabela?` | Busca scores agregados; relata. | não |
| P193 | `Procure por colunas que contenham "código" ou "code" de categorias.` | Busca campos de codificação; lista. | não |
| P194 | `Verifique se há informação de "versionamento de schema" na database.` | Busca evolução estrutural de dados; relata. | não |
| P195 | `Tem alguma fonte com dados de "sentimento" ou "sentiment_score"?` | Busca análise de sentimento; relata disponibilidade. | não |
| P196 | `Existe campo de "normalização" ou "normalized_value" em métricas?` | Busca dados normalizados; relata. | não |
| P197 | `Procure por dados de "clustering" ou "cluster_id" em segmentação.` | Busca pré-agrupamento; relata. | não |
| P198 | `Verifique se há coluna de "índice" ou "index" de desempenho.` | Busca índices compósitos; relata. | não |
| P199 | `Tem alguma informação de "validação" ou "is_valid" em dados.` | Busca flags de validação; relata. | não |
| P200 | `Procure por dados de "proveniência" ou "data_source_id" em registros.` | Busca rastreamento de origem dos dados; relata estrutura. | não |

## P201-P350: Chart Types and Dashboard Integration Tests

| ID | Prompt | Resultado esperado verificável | Após confirmação |
|---|---|---|---|
| P201 | `Crie um gráfico de linha AI_TEST_P201 de receita ao longo do tempo e adicione ao CBMES.` | Após confirmação, chart tipo linha com `transaction_date` e soma de `revenue` existe no CBMES. | sim |
| P202 | `Crie um gráfico de área AI_TEST_P202 de lucro acumulado e adicione ao CBMES.` | Após confirmação, chart tipo área com soma de `profit` de `international_sales` está no CBMES. | sim |
| P203 | `Crie um gráfico de coluna AI_TEST_P203 de vendas por território e adicione ao CBMES.` | Após confirmação, chart tipo coluna/barra com `territory` e soma de `sales` no CBMES. | sim |
| P204 | `Crie um gráfico de pizza AI_TEST_P204 de participação de vendas por produto e adicione ao CBMES.` | Após confirmação, chart tipo pizza com `product_line` e soma de `sales` está no CBMES. | sim |
| P205 | `Crie um gráfico de donut AI_TEST_P205 de distribuição de receita por região e adicione ao CBMES.` | Após confirmação, chart tipo donut com `region` e soma de `revenue` no CBMES. | sim |
| P206 | `Crie um gráfico de dispersão AI_TEST_P206 comparando price vs volume e adicione ao CBMES.` | Após confirmação, chart tipo scatter com `revenue` e `quantity` no CBMES. | sim |
| P207 | `Crie um heatmap AI_TEST_P207 de vendas por product_line e country e adicione ao CBMES.` | Após confirmação, chart tipo heatmap no CBMES com `product_line`, `country`, `sales`. | sim |
| P208 | `Crie um box plot AI_TEST_P208 de distribuição de delays por companhia aérea e adicione ao CBMES.` | Após confirmação, chart tipo box plot em `flights` com `ARRIVAL_DELAY` por `AIRLINE` no CBMES. | sim |
| P209 | `Crie um gráfico de barras horizontais AI_TEST_P209 com top 10 países por receita e adicione ao CBMES.` | Após confirmação, chart tipo bar horizontal no CBMES com `country` e `revenue`. | sim |
| P210 | `Crie uma tabela AI_TEST_P210 com detalhes de vendas por mês e adicione ao CBMES.` | Após confirmação, chart tipo tabela com dados de `cleaned_sales_data` no CBMES. | sim |
| P211 | `Crie um gráfico de radar AI_TEST_P211 comparando vendas por região (NA, EU, JP, Global) e adicione ao CBMES.` | Após confirmação, chart tipo radar com dados de `video_game_sales` ou propõe alternativa compatível no CBMES. | sim |
| P212 | `Crie um gauge AI_TEST_P212 mostrando percentual de meta de vendas e adicione ao CBMES.` | Após confirmação, chart tipo gauge no CBMES ou propõe visualização similar de KPI. | sim |
| P213 | `Crie um gráfico de treemap AI_TEST_P213 com hierarquia de vendas por categoria e país e adicione ao CBMES.` | Após confirmação, chart tipo treemap com hierarquia no CBMES ou propõe sunburst. | sim |
| P214 | `Crie um gráfico de timeline AI_TEST_P214 de eventos/marcos de vendas ao longo dos anos e adicione ao CBMES.` | Após confirmação, chart tipo timeline ou visualização temporal especial no CBMES. | sim |
| P215 | `Crie um waterfall AI_TEST_P215 mostrando contribuição de receita incremental por região e adicione ao CBMES.` | Após confirmação, chart tipo waterfall no CBMES ou propõe alternative de composição. | sim |
| P216 | `Crie um gráfico de bolhas AI_TEST_P216 com três dimensões (país, receita, população) e adicione ao CBMES.` | Após confirmação, chart tipo bubble com `country`, `revenue` (tamanho), `SP_POP_TOTL` (cor) no CBMES. | sim |
| P217 | `Crie um gráfico de caixa AI_TEST_P217 (box plot) de quantidade de pedidos por país e adicione ao CBMES.` | Após confirmação, chart tipo box plot em `cleaned_sales_data` no CBMES. | sim |
| P218 | `Crie um gráfico de sankey AI_TEST_P218 mostrando fluxo de vendas entre regiões e adicione ao CBMES.` | Após confirmação, chart tipo sankey/flow no CBMES com dados de region/country ou propõe alternativa. | sim |
| P219 | `Crie um histograma AI_TEST_P219 de distribuição de valores de receita e adicione ao CBMES.` | Após confirmação, chart tipo histogram em `international_sales` com `revenue` no CBMES. | sim |
| P220 | `Crie um gráfico de combinação AI_TEST_P220 área+linha de receita vs lucro por período e adicione ao CBMES.` | Após confirmação, chart tipo combo/mixed em `international_sales` no CBMES. | sim |
| P221 | `Crie um gráfico polar AI_TEST_P221 de vendas por mês ao longo de 3 anos e adicione ao CBMES.` | Após confirmação, chart tipo polar/radar temporal no CBMES ou propõe alternativa. | sim |
| P222 | `Crie um scatter plot AI_TEST_P222 com regression line de cost vs profit e adicione ao CBMES.` | Após confirmação, chart tipo scatter com trend line no CBMES. | sim |
| P223 | `Crie um gráfico de parede de píxeis AI_TEST_P223 (pixel heatmap) de vendas diárias e adicione ao CBMES.` | Após confirmação, chart tipo pixel heatmap ou alternativa visual similar no CBMES. | sim |
| P224 | `Crie um mapa de calor AI_TEST_P224 temporal de receita por mês e dia da semana e adicione ao CBMES.` | Após confirmação, chart tipo heatmap com `transaction_date` granularidade no CBMES. | sim |
| P225 | `Crie um gráfico de número AI_TEST_P225 (big number/KPI) mostrando receita total e adicione ao CBMES.` | Após confirmação, chart tipo big number/card com métrica agregada no CBMES. | sim |
| P226 | `Crie um gráfico de progresso AI_TEST_P226 (progress bar) de realização de meta e adicione ao CBMES.` | Após confirmação, chart tipo progress bar/linear gauge no CBMES. | sim |
| P227 | `Crie um gráfico de funil AI_TEST_P227 (funnel) mostrando etapas de vendas e adicione ao CBMES.` | Após confirmação, chart tipo funnel no CBMES com dados segmentados. | sim |
| P228 | `Crie um Pareto AI_TEST_P228 mostrando 80/20 de vendas por produto e adicione ao CBMES.` | Após confirmação, chart tipo pareto ou combo com cumulative no CBMES. | sim |
| P229 | `Crie um gráfico de velocidade AI_TEST_P229 (speedometer/gauge) de performance de vendas e adicione ao CBMES.` | Após confirmação, chart tipo speedometer/gauge no CBMES com métrica de KPI. | sim |
| P230 | `Crie um gráfico de anéis AI_TEST_P230 (ring chart) de distribuição de vendas por categoria e adicione ao CBMES.` | Após confirmação, chart tipo ring/donut com `product_category` no CBMES. | sim |
| P231 | `Crie um gráfico de barras empilhadas AI_TEST_P231 de receita por país e região e adicione ao CBMES.` | Após confirmação, chart tipo stacked bars no CBMES com dois níveis. | sim |
| P232 | `Crie um gráfico de área empilhada AI_TEST_P232 de vendas ao longo do tempo por categoria e adicione ao CBMES.` | Após confirmação, chart tipo stacked area no CBMES temporal. | sim |
| P233 | `Crie um gráfico de linha com preenchimento AI_TEST_P233 de tendência de lucro e adicione ao CBMES.` | Após confirmação, chart tipo area/line no CBMES. | sim |
| P234 | `Crie um violin plot AI_TEST_P234 de distribuição de receita por categoria e adicione ao CBMES.` | Após confirmação, chart tipo violin plot no CBMES ou propõe box plot alternativo. | sim |
| P235 | `Crie um gráfico de cobertura AI_TEST_P235 (coverage) de países atendidos sobre total e adicione ao CBMES.` | Após confirmação, chart tipo visão de cobertura/participação no CBMES. | sim |
| P236 | `Crie um dense rank AI_TEST_P236 dos top 15 produtos por receita e adicione ao CBMES.` | Após confirmação, chart tipo tabela/barra ranqueada no CBMES. | sim |
| P237 | `Crie um gráfico de calendário AI_TEST_P237 com atividades de venda por data e adicione ao CBMES.` | Após confirmação, chart tipo calendar heatmap no CBMES com vendas por data. | sim |
| P238 | `Crie um mapa geográfico AI_TEST_P238 de vendas por país e adicione ao CBMES.` | Após confirmação, chart tipo choropleth/map regional no CBMES com `country`. | sim |
| P239 | `Crie um gráfico de métricas múltiplas AI_TEST_P239 comparando 3 KPIs principais e adicione ao CBMES.` | Após confirmação, chart tipo multi-metric cards/dashboard no CBMES. | sim |
| P240 | `Crie um sunburst AI_TEST_P240 de hierarquia de vendas (país > região > categoria) e adicione ao CBMES.` | Após confirmação, chart tipo sunburst no CBMES com 3 níveis hierárquicos. | sim |
| P241 | `Crie um chord diagram AI_TEST_P241 mostrando relações entre regiões e categorias e adicione ao CBMES.` | Após confirmação, chart tipo chord diagram no CBMES ou propõe alternativa de rede. | sim |
| P242 | `Crie um network graph AI_TEST_P242 de conexões entre fornecedores e produtos e adicione ao CBMES.` | Após confirmação, chart tipo network/graph no CBMES ou propõe alternativa visual. | sim |
| P243 | `Crie um gráfico de fluxo AI_TEST_P243 (alluvial) de migração de clientes entre categorias e adicione ao CBMES.` | Após confirmação, chart tipo alluvial/flow no CBMES ou propõe sankey. | sim |
| P244 | `Crie um contour plot AI_TEST_P244 de densidade de vendas bidimensional e adicione ao CBMES.` | Após confirmação, chart tipo contour/heatmap 2D no CBMES. | sim |
| P245 | `Crie um gráfico de correlação AI_TEST_P245 (correlation matrix) entre variáveis de vendas e adicione ao CBMES.` | Após confirmação, chart tipo heatmap de correlação no CBMES. | sim |
| P246 | `Crie um PCA plot AI_TEST_P246 reduzindo dados multidimensionais e adicione ao CBMES.` | Após confirmação, chart tipo scatter PCA no CBMES ou propõe clustering visual. | sim |
| P247 | `Crie um gráfico de rosto de Chernoff AI_TEST_P247 representando múltiplas dimensões e adicione ao CBMES.` | Após confirmação, propõe visualização alternativa se não suportado; cria chart no CBMES. | sim |
| P248 | `Crie uma forma customizada AI_TEST_P248 usando dados de receita em padrão visual especial e adicione ao CBMES.` | Após confirmação, chart com visualização criativa/customizada no CBMES. | sim |
| P249 | `Crie um gráfico decorativo AI_TEST_P249 com dados de vendas em formato de arte visual e adicione ao CBMES.` | Após confirmação, chart tipo decorativo/artístico no CBMES mantendo integridade de dados. | sim |
| P250 | `Crie uma banda AI_TEST_P250 (band chart) mostrando range de variação de vendas e adicione ao CBMES.` | Após confirmação, chart tipo band/ribbon no CBMES com min-max de vendas. | sim |
| P251 | `Crie um gráfico de diferenças AI_TEST_P251 (slope chart) comparando vendas ano 1 vs ano 2 e adicione ao CBMES.` | Após confirmação, chart tipo slope/bump no CBMES. | sim |
| P252 | `Crie um dot plot AI_TEST_P252 elegante de ranking de regiões e adicione ao CBMES.` | Após confirmação, chart tipo dot plot/strip plot no CBMES. | sim |
| P253 | `Crie um swarm plot AI_TEST_P253 de distribuição de vendas por país e adicione ao CBMES.` | Após confirmação, chart tipo swarm/bee no CBMES ou propõe scatter. | sim |
| P254 | `Crie um ridgeline AI_TEST_P254 mostrando distribuição de receita ao longo do tempo e adicione ao CBMES.` | Após confirmação, chart tipo ridge/joy plot no CBMES ou propõe área. | sim |
| P255 | `Crie um gráfico de picos AI_TEST_P255 (peaks chart) de eventos de pico de vendas e adicione ao CBMES.` | Após confirmação, chart tipo linha com destaque de picos no CBMES. | sim |
| P256 | `Crie um profile plot AI_TEST_P256 mostrando tendências de 3 métricas em paralelo e adicione ao CBMES.` | Após confirmação, chart tipo linha paralela/profile no CBMES. | sim |
| P257 | `Crie um gráfico de célula AI_TEST_P257 (cell plot) de dados bimodais e adicione ao CBMES.` | Após confirmação, chart tipo grid/cell no CBMES com dados categóricos. | sim |
| P258 | `Crie um beeswarm AI_TEST_P258 com segmentação por categoria e adicione ao CBMES.` | Após confirmação, chart tipo beeswarm/swarm no CBMES com cores. | sim |
| P259 | `Crie um gráfico de folha AI_TEST_P259 (leaf chart) com dados de região e adicione ao CBMES.` | Após confirmação, propõe visualização alternativa; cria chart no CBMES. | sim |
| P260 | `Crie um streamgraph AI_TEST_P260 de evolução de vendas por categoria ao longo do tempo e adicione ao CBMES.` | Após confirmação, chart tipo stream/flowing no CBMES temporal. | sim |
| P261 | `Crie um gráfico de bolas de neve AI_TEST_P261 mostrando crescimento exponencial de um produto e adicione ao CBMES.` | Após confirmação, chart tipo bubble dinâmico ou linha exponencial no CBMES. | sim |
| P262 | `Crie um arc diagram AI_TEST_P262 com conexões entre fornecedor e cliente e adicione ao CBMES.` | Após confirmação, chart tipo arc/conexão no CBMES ou propõe sankey. | sim |
| P263 | `Crie um espaço em branco AI_TEST_P263 (whitespace chart) enfatizando alguns dados vs ruído e adicione ao CBMES.` | Após confirmação, chart com ênfase visual apropriada no CBMES. | sim |
| P264 | `Crie um gráfico em espiral AI_TEST_P264 mostrando sequência temporal de dados e adicione ao CBMES.` | Após confirmação, chart tipo espiral/radial/polar temporal no CBMES. | sim |
| P265 | `Crie um wave chart AI_TEST_P265 mostrando padrão ondulante de variação de vendas e adicione ao CBMES.` | Após confirmação, chart tipo onda/sinusoide no CBMES. | sim |
| P266 | `Crie um gráfico de fita AI_TEST_P266 (ribbon) mostrando mudanças de ranking ao longo do tempo e adicione ao CBMES.` | Após confirmação, chart tipo ribbon/bump temporal no CBMES. | sim |
| P267 | `Crie um lollipop chart AI_TEST_P267 elegante de regiões por receita e adicione ao CBMES.` | Após confirmação, chart tipo lollipop/dot-line no CBMES. | sim |
| P268 | `Crie um gráfico em explosão radial AI_TEST_P268 com dados de produto em padrão circular e adicione ao CBMES.` | Após confirmação, chart tipo radial/circular no CBMES. | sim |
| P269 | `Crie um stem plot AI_TEST_P269 mostrando série temporal com stems e adicione ao CBMES.` | Após confirmação, chart tipo stem/lollipop no CBMES com dados temporais. | sim |
| P270 | `Crie um gráfico de trilha de tempo AI_TEST_P270 de marcos de crescimento de vendas e adicione ao CBMES.` | Após confirmação, chart tipo timeline/roadmap no CBMES. | sim |
| P271 | `Crie um braço em espiral AI_TEST_P271 com dados categóricos segmentados e adicione ao CBMES.` | Após confirmação, chart tipo espiral customizada no CBMES. | sim |
| P272 | `Crie um gráfico de reflexão AI_TEST_P272 (mirror) comparando duas métricas simetricamente e adicione ao CBMES.` | Após confirmação, chart tipo pyramid/mirror no CBMES. | sim |
| P273 | `Crie um gráfico de embalagem de círculos AI_TEST_P273 (circle packing) com hierarquia de dados e adicione ao CBMES.` | Após confirmação, chart tipo circle packing/bubbles hierárquico no CBMES. | sim |
| P274 | `Crie um padrão radial AI_TEST_P274 de dados cíclicos e adicione ao CBMES.` | Após confirmação, chart tipo radial/cíclico no CBMES. | sim |
| P275 | `Crie um gráfico de gradação AI_TEST_P275 mostrando intensidade de vendas por localização e adicione ao CBMES.` | Após confirmação, chart com gradação de cores representativa no CBMES. | sim |
| P276 | `Crie um gráfico de corda AI_TEST_P276 mostrando relação de força entre entidades e adicione ao CBMES.` | Após confirmação, chart tipo chord/force no CBMES ou propõe rede. | sim |
| P277 | `Crie um gráfico polar de flores AI_TEST_P277 com dados categóricos em padrão simétrico e adicione ao CBMES.` | Após confirmação, chart tipo radar/polar floral no CBMES. | sim |
| P278 | `Crie um gráfico em cruz AI_TEST_P278 (cross plot) comparando 4 métricas em eixos e adicione ao CBMES.` | Após confirmação, chart tipo multi-eixo ou faceted scatter no CBMES. | sim |
| P279 | `Crie um gráfico ladeado AI_TEST_P279 (tilted) com ênfase em uma dimensão e adicione ao CBMES.` | Após confirmação, chart com perspectiva customizada no CBMES. | sim |
| P280 | `Crie um gráfico de triângulos AI_TEST_P280 em padrão de densidade de vendas e adicione ao CBMES.` | Após confirmação, chart tipo triangular de hexagonal heatmap no CBMES. | sim |
| P281 | `Crie um multi-gráfico AI_TEST_P281 com 4 visualizações diferentes de mesmos dados e adicione ao CBMES.` | Após confirmação, chart tipo dashboard/multi-viz com 4 perspectivas no CBMES. | sim |
| P282 | `Crie um gráfico em camadas AI_TEST_P282 (layered) mostrando sobreposição de tendências e adicione ao CBMES.` | Após confirmação, chart tipo overlay/layered com múltiplas linhas no CBMES. | sim |
| P283 | `Crie um gráfico de pequenos múltiplos AI_TEST_P283 (small multiples) de vendas por país e adicione ao CBMES.` | Após confirmação, chart tipo faceted/trellis plots no CBMES. | sim |
| P284 | `Crie um gráfico de painel AI_TEST_P284 com 6 KPIs principais lado a lado e adicione ao CBMES.` | Após confirmação, chart tipo panel/grid de cards KPI no CBMES. | sim |
| P285 | `Crie um gráfico de vento AI_TEST_P285 (wind rose) de direções de vendas por região e adicione ao CBMES.` | Após confirmação, chart tipo rose/wind rose radial no CBMES ou propõe polar. | sim |
| P286 | `Crie um gráfico de engrenagens AI_TEST_P286 mostrando integração de processos de vendas e adicione ao CBMES.` | Após confirmação, propõe visualização de processo; cria chart no CBMES. | sim |
| P287 | `Crie um gráfico de engrenajem AI_TEST_P287 (mesh) com conexões de relacionamento e adicione ao CBMES.` | Após confirmação, chart tipo network/force-directed no CBMES. | sim |
| P288 | `Crie um gráfico de crista AI_TEST_P288 (ridge) em 3D visual com dados temporais e adicione ao CBMES.` | Após confirmação, chart tipo 3D ou pseudo-3D ridge plot no CBMES. | sim |
| P289 | `Crie um gráfico de nós AI_TEST_P289 (node-link) mostrando hierarquia de dados e adicione ao CBMES.` | Após confirmação, chart tipo tree/dendrogram no CBMES. | sim |
| P290 | `Crie um gráfico de caverna AI_TEST_P290 (cave plot) com dados em ambos os lados do eixo e adicione ao CBMES.` | Após confirmação, chart tipo pyramid/diverging bar no CBMES. | sim |
| P291 | `Crie um gráfico de colméia AI_TEST_P291 (hexbin) de densidade de dados em 2D e adicione ao CBMES.` | Após confirmação, chart tipo hexbin heatmap no CBMES. | sim |
| P292 | `Crie um gráfico de espinhos AI_TEST_P292 (spike map) mostrando picos de vendas por lugar e adicione ao CBMES.` | Após confirmação, chart tipo mapa com spikes na localização no CBMES. | sim |
| P293 | `Crie um gráfico de aglomerado AI_TEST_P293 (cluster) de segmentação de clientes e adicione ao CBMES.` | Após confirmação, chart tipo scatter com clusters/cores no CBMES. | sim |
| P294 | `Crie um parallelCoordinates AI_TEST_P294 mostrando 5+ dimensões simultaneamente e adicione ao CBMES.` | Após confirmação, chart tipo parallel coordinates no CBMES. | sim |
| P295 | `Crie um gráfico de cones AI_TEST_P295 (cone chart) mostrando hierarquia invertida de vendasale adicione ao CBMES.` | Após confirmação, chart tipo cone/pyramid no CBMES. | sim |
| P296 | `Crie um gráfico de câmara AI_TEST_P296 (chamber) compartimentalizando dados por categoria e adicione ao CBMES.` | Após confirmação, chart tipo treemap ou compartilhado no CBMES. | sim |
| P297 | `Crie um gráfico de leque AI_TEST_P297 (fan) mostrando dispersão de um ponto central e adicione ao CBMES.` | Após confirmação, chart tipo radial/fan scatter no CBMES. | sim |
| P298 | `Crie um gráfico de labirinto AI_TEST_P298 (maze plot) com camado de dados segmentados e adicione ao CBMES.` | Após confirmação, propõe visualização alternativa; cria chart no CBMES. | sim |
| P299 | `Crie um gráfico de prisma AI_TEST_P299 (prism) com reflexão de dados em perspectivas diferentes e adicione ao CBMES.` | Após confirmação, chart tipo multi-perspectiva no CBMES. | sim |
| P300 | `Crie um gráfico final especial AI_TEST_P300 sintetizando todos os tipos testados em um dashboard unificado e adicione ao CBMES.` | Após confirmação, dashboard completo com múltiplas visualizações síntese é criado e publicado. | sim |
| P301 | `Crie um gráfico de impacto AI_TEST_P301 mostrando influência de variáveis sobre vendas.` | Após confirmação, chart tipo scatter com análise de impacto no CBMES. | sim |
| P302 | `Crie um gráfico de dependência AI_TEST_P302 mostrando correlações entre métricas.` | Após confirmação, chart tipo network/força com correlações no CBMES. | sim |
| P303 | `Crie um gráfico de cenários AI_TEST_P303 comparando 3 diferentes cases de vendas.` | Após confirmação, chart tipo multi-série comparativa no CBMES. | sim |
| P304 | `Crie um gráfico de margem AI_TEST_P304 mostrando distribuição de lucro por produto.` | Após confirmação, chart tipo área/empilhada com margens no CBMES. | sim |
| P305 | `Crie um mapa de fluxo AI_TEST_P305 mostrando movimento de vendas entre regiões.` | Após confirmação, chart tipo sankey/alluvial com fluxo de vendas no CBMES. | sim |
| P306 | `Crie um gráfico de quartis AI_TEST_P306 analisando distribuição de preços por categoria.` | Após confirmação, chart tipo box plot com quartis no CBMES. | sim |
| P307 | `Crie um dashboard de KPIs AI_TEST_P307 com 8 métricas principais lado a lado.` | Após confirmação, dashboard com 8 cards KPI no CBMES. | sim |
| P308 | `Crie um gráfico comparativo AI_TEST_P308 de performance YoY para análise interanual.` | Após confirmação, chart tipo coluna agrupada com comparação de anos no CBMES. | sim |
| P309 | `Crie um gráfico de contribuição AI_TEST_P309 mostrando % de cada região no total.` | Após confirmação, chart tipo estrutura de árvore com contribuições no CBMES. | sim |
| P310 | `Crie um gráfico de tendência AI_TEST_P310 com linha de regressão de vendas anual.` | Após confirmação, chart tipo linha com trend line no CBMES. | sim |
| P311 | `Crie um gráfico de estratificação AI_TEST_P311 mostrando vendas por nível de cliente.` | Após confirmação, chart tipo coluna empilhada por segmento no CBMES. | sim |
| P312 | `Crie um scorecard AI_TEST_P312 com 4 métricas de desempenho e seus targets.` | Após confirmação, dashboard com scorecards/progress bars no CBMES. | sim |
| P313 | `Crie um gráfico de crescimento AI_TEST_P313 mostrando CAGR por produto.` | Após confirmação, chart tipo linha com evolução de CAGR no CBMES. | sim |
| P314 | `Crie um gráfico de volatilidade AI_TEST_P314 mostrando variância de receita mensal.` | Após confirmação, chart tipo banda ou volatility chart no CBMES. | sim |
| P315 | `Crie um gráfico de concentração AI_TEST_P315 analisando Índice de Herfindahl por região.` | Após confirmação, chart tipo coluna com índice de concentração no CBMES. | sim |
| P316 | `Crie um dashboard de pilar AI_TEST_P316 com 5 dimensões de análise de negócio.` | Após confirmação, dashboard tipo pilar com 5 abas/seções no CBMES. | sim |
| P317 | `Crie um gráfico de atribuição AI_TEST_P317 mostrando crédito de vendas por canal.` | Após confirmação, chart tipo waterfall com atribuição no CBMES. | sim |
| P318 | `Crie um gráfico de benchmark AI_TEST_P318 comparando performance vs concorrentes.` | Após confirmação, chart tipo coluna ou radar com benchmarking no CBMES. | sim |
| P319 | `Crie um gráfico de elasticidade AI_TEST_P319 mostrando relação preço-volume.` | Após confirmação, chart tipo scatter com curva de elasticidade no CBMES. | sim |
| P320 | `Crie um painel de planejamento AI_TEST_P320 com realized vs planned.` | Após confirmação, dashboard tipo controle orçamentário no CBMES. | sim |
| P321 | `Crie um gráfico de segmentação AI_TEST_P321 mostrando RFM (recência, frequência, monetário).` | Após confirmação, chart tipo scatter 3D ou 2D matrix no CBMES. | sim |
| P322 | `Crie um gráfico de impacto temporal AI_TEST_P322 mostrando efeito de campanhas em vendas.` | Após confirmação, chart tipo linha dual-eixo com anotações no CBMES. | sim |
| P323 | `Crie um dashboard executivo AI_TEST_P323 com resumo para C-level.` | Após confirmação, dashboard estilo executivo com poucos KPIs críticos no CBMES. | sim |
| P324 | `Crie um gráfico de canal AI_TEST_P324 comparando desempenho de todos os canais.` | Após confirmação, chart tipo barra ou área por canal no CBMES. | sim |
| P325 | `Crie um mapa de calor de performance AI_TEST_P325 por produto x região.` | Após confirmação, chart tipo heatmap 2D produto vs região no CBMES. | sim |
| P326 | `Crie um gráfico de ciclo de vida AI_TEST_P326 mostrando evolução de clientes.` | Após confirmação, chart tipo sankey ou alluvial de transição no CBMES. | sim |
| P327 | `Crie um painel de operações AI_TEST_P327 com métricas de eficiência.` | Após confirmação, dashboard operacional com throughput, latência, etc no CBMES. | sim |
| P328 | `Crie um gráfico de risco AI_TEST_P328 mostrando cenários de pior/melhor caso.` | Após confirmação, chart tipo cone ou fanplot mostrando intervalos de confiança no CBMES. | sim |
| P329 | `Crie um dashboard de conformidade AI_TEST_P329 com compliance status.` | Após confirmação, dashboard tipo checklist/scorecard no CBMES. | sim |
| P330 | `Crie um gráfico de potencial AI_TEST_P330 mostrando oportunidades de growth.` | Após confirmação, chart tipo bolha ou scatter com potencial vs realizado no CBMES. | sim |
| P331 | `Crie um painel de recursos humanos AI_TEST_P331 com métricas de RH.` | Após confirmação, dashboard RH com produtividade, retenção, etc no CBMES. | sim |
| P332 | `Crie um gráfico de preferência AI_TEST_P332 mostrando produto/região preferida.` | Após confirmação, chart tipo barra top-N com preferências no CBMES. | sim |
| P333 | `Crie um dashboard de suprimentos AI_TEST_P333 com métricas de cadeia.` | Após confirmação, dashboard Supply Chain com inventário, custos, etc no CBMES. | sim |
| P334 | `Crie um gráfico de anomalia AI_TEST_P334 destacando valores atípicos de vendas.` | Após confirmação, chart tipo scatter com anomalias marcadas no CBMES. | sim |
| P335 | `Crie um painel de inovação AI_TEST_P335 mostrando produtos novos vs maduros.` | Após confirmação, dashboard com ciclo de vida de inovação no CBMES. | sim |
| P336 | `Crie um gráfico de lealdade AI_TEST_P336 analisando repeat purchase rate.` | Após confirmação, chart tipo linha ou área mostrando padrão de lealdade no CBMES. | sim |
| P337 | `Crie um dashboard de riscos AI_TEST_P337 com heat maps de exposição.` | Após confirmação, dashboard tipo risk matrix com priorização no CBMES. | sim |
| P338 | `Crie um gráfico de valor agora esperado AI_TEST_P338 com NPV por projeto/produto.` | Após confirmação, chart tipo coluna com ranking NPV no CBMES. | sim |
| P339 | `Crie um painel de sustentabilidade AI_TEST_P339 com métricas ESG.` | Após confirmação, dashboard com indicadores de sustentabilidade no CBMES. | sim |
| P340 | `Crie um gráfico de crosssell AI_TEST_P340 mostrando oportunidades de venda cruzada.` | Após confirmação, chart tipo rede ou correlated items no CBMES. | sim |
| P341 | `Crie um dashboard de retenção AI_TEST_P341 com churn analysis.` | Após confirmação, dashboard com cohort analysis e retenção no CBMES. | sim |
| P342 | `Crie um gráfico de score AI_TEST_P342 com ranking de clientes por value.` | Após confirmação, chart tipo tabela ranqueada com propriedades no CBMES. | sim |
| P343 | `Crie um painel de inovação digital AI_TEST_P343 com métricas tech.` | Após confirmação, dashboard com adoção de tecnologia, digitalizaçãoetc no CBMES. | sim |
| P344 | `Crie um gráfico de afinidade AI_TEST_P344 mostrando co-ocorrência de produtos.` | Após confirmação, chart tipo correção de afinidade ou association rules no CBMES. | sim |
| P345 | `Crie um dashboard de diversidade AI_TEST_P345 com índices de mix de portfólio.` | Após confirmação, dashboard mostrando diversificação de receita no CBMES. | sim |
| P346 | `Crie um gráfico de persistência AI_TEST_P346 mostrando durabilidade de receita.` | Após confirmação, chart tipo área ou coluna empilhada mostrando permanência no CBMES. | sim |
| P347 | `Crie um painel de satisfação AI_TEST_P347 com NPS e CSAT por segmento.` | Após confirmação, dashboard com scores de satisfação no CBMES. | sim |
| P348 | `Crie um gráfico de viabilidade AI_TEST_P348 comparando projetos por ROI vs risco.` | Após confirmação, chart tipo bolha com viabilidade de projetos no CBMES. | sim |
| P349 | `Crie um dashboard integrado AI_TEST_P349 unificando perspectivas financeira e operacional.` | Após confirmação, dashboard full-stack com multidimensão financeira+ops no CBMES. | sim |
| P350 | `Crie um gráfico de síntese AI_TEST_P350 resumindo indicador de performance geral (GPI).` | Após confirmação, chart tipo scorecard ou gauge mostrando GPI consolidado no CBMES. | sim |

## P351-P500: Direct Chat Queries (Read-Only, No Artifacts)

| ID | Prompt | Resultado esperado verificável | Após confirmação |
|---|---|---|---|
| P351 | `Qual é a receita total de international_sales em todo o período?` | Retorna valor agregado de soma de `revenue` sem criar chart ou dataset. | não |
| P352 | `Quantos produtos diferentes existem em cleaned_sales_data?` | Calcula contagem distinta de `product_line` (ou similar) e responde numericamente. | não |
| P353 | `Qual região gerou mais lucro em international_sales?` | Agrega `profit` por `region`, retorna top 1 com valor absoluto. | não |
| P354 | `Qual foi o padrão de vendas ao longo dos meses em 2023?` | Descreve tendência mensal de `sales` ou `revenue` em 2023 sem visualização. | não |
| P355 | `Explique as colunas disponíveis em video_game_sales e como usá-las.` | Descreve schema de `video_game_sales` com tipos de dados e possibilidades analíticas. | não |
| P356 | `Qual country tem maior população segundo wb_health_population?` | Retorna país com maior `SP_POP_TOTL` e valor correspondente. | não |
| P357 | `Qual é a média de atraso de chegada nas companhias aéreas?` | Calcula média de `ARRIVAL_DELAY` por `AIRLINE` ou geral e responde. | não |
| P358 | `Compare as receitas de north america, europa e japan em video_game_sales.` | Soma `na_sales`, `eu_sales`, `jp_sales` e apresenta comparação com valores. | não |
| P359 | `Qual produto teve pior performance em termos de profit?` | Identifica `product_category` ou `product_name` com menor `profit` agregado. | não |
| P360 | `Calcule o ticket médio de vendas por país em international_sales.` | Divide soma de `revenue` por contagem de registros por país; retorna valores. | não |
| P361 | `Quantos voos foram cancelados em flightos em 2016?` | Filtra por ano e soma `CANCELLED` ou contagem de registros cancelados. | não |
| P362 | `Qual é o crescimento de vendas entre o primeiro e o último ano disponível?` | Calcula percentual de variação entre períodos iniciais e finais. | não |
| P363 | `Determine o país com menores custos de operação em international_sales.` | Ordena por `cost` agregado e retorna país com menor valor. | não |
| P364 | `Qual foi o ano com mais nascimentos registrados em birth_names?` | Agrega `num` por `year` e retorna o ano com maior soma. | não |
| P365 | `Compare as expectativas de vida entre continentes ous regiões.` | Retorna `SP_DYN_LE00_IN` por `region` de `wb_health_population` ou agrupado. | não |
| P366 | `Qual genre de videogame vendeu mais cópias globalmente?` | Retorna `genre` com maior soma de `global_sales`. | não |
| P367 | `Qual é a taxa de cancelamento de voos em flights?` | Calcula percentual de voos cancelados sobre total. | não |
| P368 | `Quais são os 3 territórios com maior participação em cleaned_sales_data?` | Retorna top 3 de `territory` por soma de `sales`. | não |
| P369 | `Qual plataforma de videogames tem melhor média de vendas por título?` | Ordena `platform` por média de `global_sales` e retorna top 1. | não |
| P370 | `Qual foi o mês com maior receita consolidada?` | Filtra melhor mês de soma de `revenue` ou `sales` agregado. | não |
| P371 | `Explique a correlação entre revenue e quantity em international_sales.` | Descreve relação sem calcular; oferece interpretação lógica. | não |
| P372 | `Qual é a margem média de lucro por região?` | Calcula `SUM(profit)/SUM(revenue)` por `region` e retorna percentuais. | não |
| P373 | `Quantos registros únicos de países existem nas fontes de dados?` | Conta DISTINCT de columnas de país em diferentes tabelas. | não |
| P374 | `Qual editora de jogos vendeu mais cópias totais em video_game_sales?` | Agrega `global_sales` por `publisher` e retorna top 1. | não |
| P375 | `Qual foi a maior distância de voo registrada em flights?` | Retorna máximo valor de `DISTANCE`. | não |
| P376 | `Qual é o desvio padrão de atrasos de partida em flights?` | Calcula dispersão estatística de `DEPARTURE_DELAY`. | não |
| P377 | `Descreva a distribuição de vendas entre as linhas de produto.` | Retorna participação e contagem de cada `product_line`. | não |
| P378 | `Qual série temporal melhor descreve o crescimento de lucro?` | Propõe análise de tendência; describe padrão sem visualizar. | não |
| P379 | `Qual é a receita máxima em uma única transação de international_sales?` | Retorna MAX de `revenue`. | não |
| P380 | `Quantos nomes de bebês diferentes foram registrados por gênero em birth_names?` | Conta DISTINCT de `name` por `gender`. | não |
| P381 | `Qual estado tem mais nascimentos registrados em birth_names?` | Agrega `num` por `state` e retorna top 1. | não |
| P382 | `Calcule a taxa de atrasos em voos por companhia aérea.` | Calcula percentual de voos com delay > 0 por `AIRLINE`. | não |
| P383 | `Qual foi o performance média de lucro vs receita em cada região?` | Calcula margem média de lucro (`profit/revenue`) por `region` sem chart. | não |
| P384 | `Quantas transações únicas foram registradas por país?` | Conta registros por `country` em `international_sales`. | não |
| P385 | `Qual é a idade (em anos) dos dados de voos (flygtime range)?` | Retorna ano inicial e final de dados em `flights`. | não |
| P386 | `Qual categoria de produto tem melhor margem de lucro?` | Calcula `profit/revenue` por `product_category` e retorna top 1. | não |
| P387 | `Explicar o impacto de quantidade vendida sobre profit.` | Descreve relação entre `quantity` e `profit` interpretativamente. | não |
| P388 | `Qual é a receita acumulada até o final de cada trimestre?` | Calcula soma acumulada de `revenue` por trimestre de `transaction_date`. | não |
| P389 | `Qual companhia aérea tem o pior histórico de cancelamentos?` | Retorna `AIRLINE` com maior taxa de `CANCELLED`. | não |
| P390 | `Quais são as top 5 combinações país + categoria por receita?` | Retorna top 5 de `country`, `product_category` por soma `revenue`. | não |
| P391 | `Qual foi a media de quantidade vendida por pedido?` | Calcula média de `quantity_ordered` (ou similar) por transação. | não |
| P392 | `Qual indicador de saúde (SP_DYN_MORT, SP_POP_TOTL, etc.) varia mais entre países?` | Analisa variância de indicadores de `wb_health_population` e descreve. | não |
| P393 | `Qual é a taxa de crescimento mensal médio de vendas?` | Calcula MoM variação média de serie temporal de `sales` ou `revenue`. | não |
| P394 | `Qual gênero de videogame tem melhor taxa de venda por plataforma?` | Calcula média de `global_sales` por combinação `genre` + `platform`. | não |
| P395 | `Qual mês do ano historicamente tem melhor performance de vendas?` | Agrega `sales` ou `revenue` por mês (janeiro, fevereiro, etc) ano-a-ano. | não |
| P396 | `Qual % de vendas são provenientes do top 10 produtos?` | Calcula participação de top 10 de `product_name`/categoria sobre total. | não |
| P397 | `Qual é a receita média por transação e seu desvio padrão?` | Calcula `AVG(revenue)` e desvio padrão sem visualização. | não |
| P398 | `Qual foi o melhor e o pior trimestre do ano em termos de lucro?` | Compara trimestres e retorna máximo e mínimo. | não |
| P399 | `Qual país teve maior crescimento percentual de vendas YoY?` | Calcula variação ano-a-ano por país e retorna maior. | não |
| P400 | `Quantos registros de voos correspondem a rotas nacionais vs internacionais?` | Segmenta `flights` por tipo de rota e retorna contagem. | não |
| P401 | `Qual foi o percentual de devoluções/cancelamentos em cleaned_sales_data?` | Filtra `status` de cancelado/(rejeitado e calcula taxa. | não |
| P402 | `Qual é a receita por capita de cada região usando dados de população?` | Junta `international_sales` e `wb_health_population`, calcula ratio. | não |
| P403 | `Qual companhia aérea tem menor variação de atraso (mais consistente)?` | Calcula desvio padrão de `ARRIVAL_DELAY` e `DEPARTURE_DELAY` por `AIRLINE`. | não |
| P404 | `Qual é o ranking de performance dos 10 países por receita?` | Lista 10 países em ordem descendente de `revenue` agregada. | não |
| P405 | `Qual é o padrão sazonal de declínio ou crescimento de voos?` | Describe padrão de `YEAR`/`MONTH` sem gráfico de sazonalidade. | não |
| P406 | `Qual gênero de bebê foi mais frequente em cada década?` | Agrega por decade de `ds` (ou year em grupos) por `gender`. | não |
| P407 | `Qual é a receita média dos top 5 países versus a mediana geral?` | Compara média do top 5 com mediana de todos os dados. | não |
| P408 | `Qual foi a quantidade total de itens movimentados em cleaned_sales_data?` | Soma `quantity_ordered` ou equivalente total. | não |
| P409 | `Qual padrão de custo vs receita define as regiões mais lucrativas?` | Descreve relação sem visualizar; analisa estrutura de lucro. | não |
| P410 | `Qual é o valor de transação típico (P25, P50, P75) por país?` | Calcula percentis de `revenue` por `country`. | não |
| P411 | `Qual companhia aérea cresceu mais em volume de voos ao longo dei anos?` | Compara volume de `flights` por `AIRLINE` entre anos. | não |
| P412 | `Qual categoria de produto tem maior seasonalidade?` | Descreve variação sazonal por `product_category` sem gráfico. | não |
| P413 | `Qual é o top 3 de regiões por margem de lucro?` | Ranking de `region` por `SUM(profit)/SUM(revenue)` em descending. | não |
| P414 | `Quanto representam as "vendas online" versus "física" se houver segmentação?` | Busca campo de channel/tipo; se não existir, informa ausência. | não |
| P415 | `Qual foi o crescimento absoluto e percentual de receita YTD?` | Calcula variação desde início de ano até data mais recente. | não |
| P416 | `Qual país tem maior população por `resident`?` | Retorna país com maior `SP_POP_TOTL` e valor numérico. | não |
| P417 | `Qual benchmark internacional de vendas por capita você sugere usar?` | Oferece análise contextual sem criar artefatos analíticos. | não |
| P418 | `Qual distribuição de dados de atrasos em flights é mais normal?` | Descreve forma de distribuição de `DEPARTURE_DELAY` vs `ARRIVAL_DELAY`. | não |
| P419 | `Qual é o ROI potencial por região baseado em receita vs custo?` | Calcula índice de rentabilidade (`revenue/cost`) por `region`. | não |
| P420 | `Qual fonte de dados seria opcional remover se houvesse limite de recursos?` | Oferece análise comparativa de tamanho/importância das bases. | não |
| P421 | `Qual foi a volatilidade de preço/receita ao longo do período?` | Descreve variação de `revenue` per transaction sem gráfico. | não |
| P422 | `Quantos usuários únicos ou compradores existem em cleaned_sales_data?` | Conta DISTINCT de identificador de cliente se disponível, ou registros únicos. | não |
| P423 | `Qual é o intervalo de confiança 95% para a receita média?` | Calcula estatística de intervalo sem visualização. | não |
| P424 | `Qual padrão de correlação existe entre `cost`, `profit` e `revenue`?` | Descreve relação multivariada sem matriz visual. | não |
| P425 | `Qual foi o pior mês para cada companhia aérea em termos de atrasos?` | Identifica mês/airline com maior média de delay. | não |
| P426 | `Qual segmento de cliente (por receita) é mais volátil em termos de comportamento?` | Propõe análise de segmentação; retorna interpretação sem artefato. | não |
| P427 | `Qual é a expectativa de vida global média segundo dados de população?` | Cálcula média de `SP_DYN_LE00_IN` de `wb_health_population`. | não |
| P428 | `Qual é a mediana de receita por transação em cada país?` | Calcula P50 de `revenue` por `country`. | não |
| P429 | `Qual foi a participação de mercado por editora de games em 2023 (se houver)?` | Agrega `global_sales` por `publisher` para período (se dados permitrem). | não |
| P430 | `Qual é o coeficiente de variação de lucro entre regiões?` | Calcula fórmula estatística de desvio/média sem chart. | não |
| P431 | `Qual foi o impacto de cancelamentos de voos em volume total?` | Compara volume total vs volume de voos cancelados (em %). | não |
| P432 | `Qual foi a maior variação de receita entre dois meses consecutivos?` | Identifica pico de mudança mensal histórica. | não |
| P433 | `Qual é a quantidade de transações por hora do dia (se granulação permitir)?` | Descreve padrão intra-dia se dados de hora estão disponíveis. | não |
| P434 | `Qual nome de bebê foi ranking #1 em cada década de 1960 a 2020?` | Retorna top name por década de `birth_names`. | não |
| P435 | `Qual é a distância média de voo por companhia aérea?` | Calcula `AVG(DISTANCE)` por `AIRLINE`. | não |
| P436 | `Qual país tem menores gastos de saúde per capita (SH_DYN_MORT) relativos?` | Retorna país com melhor correlação entre população e indicadores de saúde. | não |
| P437 | `Qual foi a receita acumulada (running total) mês a mês?` | Retorna série acumulada de receita sem visualização. | não |
| P438 | `Qual gênero de bebê foi mais popular segundo nomes únicos registrados?` | Conta DISTINCT de `name` por `gender` e retorna proporção. | não |
| P439 | `Qual platform vendeu melhor em NA vs EU em video_game_sales?` | Compara `na_sales` vs `eu_sales` por `platform`. | não |
| P440 | `Qual foi o padrão de lucro acumulado ao longo dos anos?` | Descreve série acumulada de `profit` sem visualizar. | não |
| P441 | `Qual é a elasticidade preço-demanda se houver dados de preço?` | Oferece análise teórica; informa se dados permitem cálculo. | não |
| P442 | `Qual é a taxa de retenção de categorias de produto (vendas repetidas)?` | Analisa se dados permittem; retorna taxa sem criar recurso. | não |
| P443 | `Qual foi o maior ticket de venda e em qual país/contexto?` | Retorna MAX de `revenue` com contexto de país/categoria. | não |
| P444 | `Qual companhia aérea é mais afetada por atrasos de chegada que de partida?` | Compara médias de `ARRIVAL_DELAY` vs `DEPARTURE_DELAY` por `AIRLINE`. | não |
| P445 | `Qual foi o desempenho de lucro acumulado do 1T vs 2T vs 3T vs 4T?` | Retorna somas trimestrais sem visualização. | não |
| P446 | `Qual percentual da receita total vem dos 30% de transações de maior valor?` | Calcula Pareto (80/20) sem gráfico. | não |
| P447 | `Qual é a tendência de crescimento de população no último século em wb_health_population?` | Descreve trajetória de `SP_POP_TOTL` sem gráfico. | não |
| P448 | `Qual foi o custo total de operação em international_sales?` | Soma total de `cost`. | não |
| P449 | `Qual padrão semanal existe em dados de voos (dia da semana)?` | Descreve padrão se field de dia da semana está disponível. | não |
| P450 | `Qual é a concentração de vendas (HHI - Herfindahl Index) por região?` | Calcula índice de concentração de mercado sem visualização. | não |
| P451 | `Qual foi o desempenho de nomes de bebês por década no século XX?` | Descreve padrão de popularidade por período sem chart. | não |
| P452 | `Qual foi a mortalidade infantil média por região segundo dados de população?` | Calcula média de `SH_DYN_MORT` por `region`. | não |
| P453 | `Qual é o impacto de distância de voo em atrasos (correlação)?` | Describe relação entre `DISTANCE` e `ARRIVAL_DELAY` interpretatively. | não |
| P454 | `Qual foram as 5 maiores transações por valor em international_sales?` | Retorna top 5 de MAX `revenue` sem criar chart. | não |
| P455 | `Qual foi o mês em que video_game_sales foi maior globalmente?` | Identifica melhor período se dados permittem granularidade. | não |
| P456 | `Qual é a média de lucro por pedido em cleaned_sales_data?` | Retorna `AVG(profit)` aggregating if needed. | não |
| P457 | `Qual foi a taxa de crescimento de vendas CAGR (Compound Annual Growth Rate)?` | Calcula CAGR entre primeiro e último período disponível. | não |
| P458 | `Qual country tem melhor expectativa de vida segundo dados?` | Retorna país com MAX de `SP_DYN_LE00_IN`. | não |
| P459 | `Qual foi a receita média semanal se houver granularidade de data?` | Calcula `AVG(revenue)` por semana sem visual. | não |
| P460 | `Qual é a performance de cada categoria em termos de ROI?` | Calcula `profit/cost` por `product_category`. | não |
| P461 | `Qual mês tem histórico de mais atrasos em flights?` | Agrega `MONTH`/`ds` por média de delay. | não |
| P462 | `Qual foi o nome de bebê que cresceu mais em popularidade entre décadas?` | Identifica maior variação de `num` por `name` entre períodos. | não |
| P463 | `Qual é a população global total segundo wb_health_population?` | Soma `SP_POP_TOTL` de todos os países por year. | não |
| P464 | `Qual foi a maior margem de lucro unitária em uma transação de vendas?` | Retorna MAX de `(revenue - cost) / quantity`. | não |
| P465 | `Qual foi o volume de vendas total por status (concluído, cancelado, etc)?` | Agrega `sales` ou `quantity` por `status`. | não |
| P466 | `Qual é a distribuição de atrasos (percentis: 10, 25, 50, 75, 90) em flights?` | Retorna distribuição estatística sem gráfico. | não |
| P467 | `Qual foi o crescimento de receita em % no melhor ano em relação ao anterior?` | Identifica ano com maior YoY % variação. | não |
| P468 | `Qual estado tem menor população segundo dados de nascimentos?` | Retorna estado com menor agregação de `num` em `birth_names`. | não |
| P469 | `Qual foi o custo médio por unidade vendida em cada região?` | Calcula `SUM(cost)/SUM(quantity)` por `region`. | não |
| P470 | `Qual foi o percentual de voos com atraso acima de 30 minutos?` | Calcula proporção onde `ARRIVAL_DELAY` > 30 min. | não |
| P471 | `Qual é o índice de diversidade de produtos em cada país?` | Calcula número único de produtos/categorias por país. | não |
| P472 | `Qual foi a receita do melhor dia registrada em international_sales?` | Retorna MAX de `revenue` agregada por `transaction_date`. | não |
| P473 | `Qual companhia aérea cancelou menos voos em proporção?` | Calcula `CANCELLED/TOTAL` por `AIRLINE`; retorna MIN. | não |
| P474 | `Qual foi a diminuição na expectativa de vida entre 2000 e 2020 (se comparável)?` | Calcula diferença se dados permittem evolução temporal. | não |
| P475 | `Qual foi o desempenho de receita per capita por país e ano?` | Junta dados e calcula ratio sem visualizar. | não |
| P476 | `Qual foi a quantidade média de produtos por pedido?` | Calcula `AVG(quantity_ordered)`. | não |
| P477 | `Qual foi o percentual de crescimento de atrasos ao longo dos anos em flights?` | Descreve evolução temporal de `ARRIVAL_DELAY` sem visual. | não |
| P478 | `Qual foi a contribuição de cada região para o lucro total?` | Calcula participação `profit/total_profit` por `region`. | não |
| P479 | `Qual país tem a menor taxa de mortalidade infantil?` | Retorna país com MIN de `SH_DYN_MORT`. | não |
| P480 | `Qual foi a lacuna máxima entre receita esperada (média) e realizada?` | Calcula desvio máximo sem criar artefato. | não |
| P481 | `Qual foi a receita média trimestral e sua variação?` | Calcula `AVG(revenue)` por trimestre com desvio. | não |
| P482 | `Qual serie temporal de vendas (por mês) melhor se ajusta a trend exponencial ou linear?` | Oferece análise descritiva sem regressão visual. | não |
| P483 | `Qual foi a quantidade de transações únicas por ano?` | Conta registros por `YEAR` ou anual. | não |
| P484 | `Qual gênero de videogame representa maior % do total de vendas?` | Calcula participação de cada `genre` sobre `global_sales` total. | não |
| P485 | `Qual é o nível de "concentração de clientes" em cleaned_sales_data (top 20% gera quantos %)?` | Calcula participação de top quintil sem gráfico. | não |
| P486 | `Qual foi a receita de vendas "ao vivo" em tempo real (última data disponível) por região?` | Retorna receita mais recente por `region`. | não |
| P487 | `Qual foi a escala de lucro em comparação a receita (profit/revenue) geral?` | Calcula ratio global de margem. | não |
| P488 | `Qual país experimentou maior mudança em expectativa de vida entre 1990 e 2020?` | Calcula delta se períodos disponíveis; retorna país com maior variação. | não |
| P489 | `Qual foi a receita média máxima diária do melhor mês?` | Filtra melhor mês e retorna MAX diária naquele período. | não |
| P490 | `Qual é o percentual de transações de alto valor (acima do P90) em cada região?` | Calcula proporção de transações > P90 por `region`. | não |
| P491 | `Qual performance de atrasos para rotas de longa distância vs curta distância?` | Segmenta `flights` por `DISTANCE` e compara `ARRIVAL_DELAY`. | não |
| P492 | `Qual foi o crescimento absoluto de população global no último período?` | Calcula diferença de `SP_POP_TOTL` entre períodos recentes. | não |
| P493 | `Qual foi a receita média por categoria em relação à receita global média?` | Compara `AVG(revenue)` por `product_category` vs global média. | não |
| P494 | `Qual mês historicamente tem menor receita (sazonalidade baixa)?` | Identifica mês com menor agregação de `revenue`/`sales` histórica. | não |
| P495 | `Qual foi o volume de voos cancelados vs não-cancelados em proporção?` | Retorna percentuais de ambas as categorias. | não |
| P496 | `Qual foi a população juvenil (índice de natalidade) por estado segundo birth_names?` | Agrega `num` por `state` por `gender` para mensurar. | não |
| P497 | `Qual país perdeu população entre a medição inicial e final?` | Identifica países com DELETE de `SP_POP_TOTL` negativa ao longo do tempo. | não |
| P498 | `Qual foi a volatilidade (desvio padrão) de `revenue` por `country` agregado?` | Calcula desvio por país sem visualização. | não |
| P499 | `Qual foi o valor de transação atípico (outlier) mais extremo em international_sales?` | Identifica máximo ou mínimo estatístico extremo. | não |
| P500 | `Resuma os 5 principais insights des análise exploratória das bases de dados de examples.` | Oferece resumo executivo descritivo de padrões principais identificados. | não |

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
