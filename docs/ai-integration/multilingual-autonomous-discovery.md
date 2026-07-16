# Especificação — Descoberta Multilíngue e Plano Analítico Autônomo

## Problema

Na primeira interação, um pedido genérico como:

> Elabore um gráfico em barras das vendas por ano.

não deve exigir que a pessoa usuária conheça ou informe o nome da tabela. O
assistente precisa localizar fontes acessíveis relacionadas ao tema, mesmo
quando o prompt e os metadados estão em idiomas diferentes. A solução deve
funcionar para pt-BR, en-US, es-ES e fr-FR e não pode modificar qualquer dado
ou metadado persistido no banco.

## Resultado esperado

Com um único prompt, o sistema deve:

1. entender a intenção analítica (tema, métrica, dimensão temporal,
   visualização e eventual destino);
2. descobrir e pontuar fontes de dados permitidas, em todos os bancos
   acessíveis, datasets e consultas salvas do usuário;
3. selecionar uma fonte quando a confiança for suficiente ou oferecer
   alternativas concretas quando não for;
4. montar um plano completo e validado;
5. pedir uma única aprovação para todos os efeitos de escrita;
6. executar o plano, publicar progresso parcial e apresentar os links do
   resultado.

O Ollama participa da interpretação do pedido e da explicação do resultado. A
busca, ranking, validação e construção dos payloads de Superset permanecem
determinísticos no backend.

## Descoberta multilíngue sem alterar dados

Cada termo do pedido gera uma `DiscoveryQuery` efêmera. Ela contém o texto
original, idioma configurado do agente, forma normalizada, sinônimos e traduções
controladas. A normalização ocorre somente em memória:

- remover diferenças de caixa, acentos e pontuação;
- tratar `_`, `-` e espaços como separadores equivalentes;
- considerar singular/plural e tokens compostos;
- preservar o valor original para exibição e para qualquer chamada ao Superset.

Exemplo para o tema `vendas`:

```text
vendas | venda | sales | sale | ventas | venta | ventes | vente
```

O dicionário multilíngue cobre termos analíticos frequentes e é versionado no
backend. Quando necessário, o provedor pode sugerir expansão semântica, mas
somente dentro de limites de tamanho e idioma; indisponibilidade ou baixa
confiança não interrompe a descoberta lexical local.

Nenhuma tradução é gravada em `Database`, `SqlaTable`, `SavedQuery`, chart ou
dashboard. Nomes como `international_sales`, `Vendas Internacionais`,
`ventas_anuales` e `ventes_annuelles` continuam intactos.

## Fontes pesquisadas e regras de segurança

O serviço de descoberta busca apenas recursos que o usuário já pode acessar:

| Tipo | Campos usados para descoberta | Dados expostos ao modelo |
|---|---|---|
| Banco | nome e backend | nome seguro e identificador interno validado |
| Tabela | nome, schema e colunas permitidas | metadados de schema, nunca linhas brutas |
| Dataset | nome, descrição e colunas | metadados e perfil agregado limitado |
| Saved query | rótulo, descrição, SQL já autorizado, tabelas/aliases e schema de resultado limitado | resumo seguro; SQL sanitizado e mínimo |

RBAC, permissões de banco/datasource, RLS e visibilidade das consultas salvas
são aplicados antes do ranking. Recursos não acessíveis não aparecem como
candidatos e não entram no prompt do Ollama.

### Correspondência por conteúdo estrutural

O nome de uma fonte é apenas um sinal. Uma tabela chamada `fato_001`, um dataset
chamado `base_comercial` ou uma consulta chamada `relatorio_final` ainda podem
ser a melhor fonte para o tema “vendas” se suas colunas indicarem isso. A
descoberta inicial deve, portanto, buscar também em:

- nomes, descrições e tipos de colunas de tabelas e datasets;
- aliases e colunas de resultado inferidas de saved queries autorizadas;
- tabelas de origem de uma saved query, quando a análise do SQL permitida
  conseguir identificá-las;
- compatibilidade estrutural com a intenção: data/ano, valor monetário,
  quantidade, identificador de pedido/venda e dimensões relacionadas.

Por exemplo, `fato_001(order_date, total_amount, order_id)` deve ser candidato
para “vendas por ano” mesmo sem a palavra `vendas` no nome. Já o conteúdo de
linhas não é usado na busca inicial. Se necessário, um perfil agregado e
limitado confirma a hipótese depois que o candidato passa pelas permissões.

## Ranking e decisão

O ranking é reproduzível e justificado. Ele combina:

1. correspondência exata e normalizada de nome;
2. equivalência por sinônimo/tradução;
3. aderência entre palavras do tema e nomes/descrições/colunas;
4. compatibilidade com a intenção — por exemplo, coluna temporal e medida ou
   identificador para “quantidade por ano”;
5. contexto da página e nomes explicitamente mencionados pela pessoa usuária.

O sinal de colunas/estrutura pode superar o sinal de nome quando o nome for
genérico, mas não pode ignorar incompatibilidades: um candidato sem coluna de
tempo não é adequado para “por ano”, salvo se houver uma alternativa explícita
apresentada à pessoa usuária.

Uma fonte só é selecionada automaticamente se atingir o limiar de confiança e
superar a segunda colocada por margem configurada. Caso contrário, o chat mostra
no máximo três alternativas, por exemplo:

```text
Encontrei duas fontes adequadas para “vendas por ano”:
1. Dataset international_sales (Examples) — colunas: order_date, sales, order_id
2. Tabela ventas_anuales (Comercial) — colunas: año, importe, id_venta

Qual delas deseja utilizar?
```

Se nenhuma fonte for encontrada, a resposta informa quais tipos e idiomas foram
pesquisados e pede uma referência opcional, sem inventar uma tabela.

## Catálogo derivado de metadados e frescor

O catálogo não é uma lista fechada de temas conhecidos pelo sistema. Ele é um
índice derivado **por fonte** que pode reduzir significativamente a busca em
instâncias com muitas fontes, mas não deve se tornar uma cópia permanente e
desatualizada da estrutura dos bancos. Cada entrada indexa metadados seguros de
uma fonte — nomes normalizados, colunas, tipos, aliases permitidos, idiomas
detectados, temas inferidos, versão e data de atualização. Os temas são sinais
de ranking, não critérios de inclusão ou exclusão.

A estratégia recomendada é incremental:

1. **Primeiro, descoberta ao vivo (Fase 7.1–7.5).** A correção funcional usa
   schemas e metadados acessíveis no momento do pedido. Isso garante que uma
   nova coluna ou alteração de estrutura seja considerada imediatamente.
2. **Depois, catálogo derivado (Fase 7.6).** Armazenar apenas o índice seguro
   de metadados já permitidos. Um tema é inferido desses metadados quando a
   fonte é indexada ou quando a consulta é feita; não há uma taxonomia que
   precise ser preenchida previamente pela pessoa usuária. Ele não altera nem
   substitui os objetos do Superset.
3. **Usar como aceleração, nunca como verdade final.** O catálogo faz
   pré-seleção e ranking; antes do plano e sempre antes de uma escrita, o
   backend relê schema, existência e permissões ao vivo.

O catálogo deve expirar por TTL e ser invalidado quando houver alteração ou
sincronização de database/dataset/saved query, além de oferecer reconstrução
manual ao administrador. Sem versão conhecida, catálogo ausente ou candidato
possivelmente desatualizado, o fluxo retorna à descoberta ao vivo.

### Tema inédito e fonte ainda não catalogada

Toda solicitação começa com uma busca híbrida:

```text
candidatos do catálogo fresco
+ fontes criadas/alteradas desde a última indexação
+ fontes sem entrada no catálogo
+ varredura ao vivo quando não houver confiança suficiente
```

Assim, se alguém pedir pela primeira vez “inadimplência”, “emissões de carbono”
ou qualquer outro tema não conhecido, a expansão multilíngue e a busca ao vivo
percorrem os metadados autorizados de todas as fontes acessíveis. Os candidatos
encontrados podem alimentar o catálogo como consequência da descoberta, mas a
resposta não depende de esse tema já existir nele.

Da mesma forma, uma tabela, dataset ou saved query recém-criada não é ignorada:
ela entra pelo conjunto de fontes novas/alteradas ou pela varredura ao vivo. O
catálogo pode reduzir a quantidade de schemas consultados, mas jamais pode ser
usado como filtro que exclui fontes não indexadas. Quando houver dúvida de
frescor ou baixa confiança, a busca ao vivo prevalece.

Assim, a otimização é planejada desde já, mas fica para depois da implementação
e medição do fluxo correto. Isso evita gastar tempo indexando uma lógica de
ranking ainda em evolução e preserva a capacidade de refletir mudanças recentes
nas fontes.

## Plano e confirmação única

Após a seleção, o backend gera um plano imutável. Para o pedido de gráfico de
vendas por ano, um plano típico é:

```text
descobrir fontes relacionadas a vendas
→ validar schema de international_sales
→ identificar order_date e sales/order_id
→ definir barras e agregação anual
→ criar ou reutilizar dataset necessário
→ criar chart
→ adicionar ao dashboard, se solicitado
→ aguardar confirmação única
→ executar e apresentar links
```

O plano mostra a fonte escolhida, as colunas usadas, a agregação, os recursos a
criar/reutilizar e o dashboard de destino. O frontend só mostra os botões
**Confirmar plano** e **Cancelar** quando todos os parâmetros de escrita já
passaram pela validação de backend. Texto gerado pelo modelo nunca vale como
confirmação.

Após a confirmação, o executor processa as etapas de forma sequencial,
idempotente e auditável. Falhas interrompem as posteriores e indicam a etapa e
o motivo seguro no chat.

## Progresso no chat

Enquanto a tarefa estiver ativa, uma única mensagem atualizável informa a etapa:

```text
Procurando fontes relacionadas a “vendas” em bancos, datasets e consultas
Encontrei international_sales; validando colunas de tempo e vendas
Plano pronto: criar gráfico anual de barras usando international_sales
Aguardando sua aprovação para criar e publicar os recursos
```

A animação de processamento permanece ativa em descoberta, análise,
planejamento e execução. Ela é removida apenas ao aguardar escolha/confirmação,
na conclusão ou na falha.

## Cenários de aceitação

| Prompt | Comportamento esperado |
|---|---|
| “Elabore um gráfico em barras das vendas por ano.” | Descobre `international_sales`/fontes equivalentes antes de qualquer pergunta; propõe fonte ou alternativas. |
| “Create a yearly sales bar chart.” | Produz os mesmos candidatos de `vendas`, apesar do prompt em inglês. |
| “Haz un gráfico de ventas por año.” | Busca `sales`, `vendas` e `ventes`, respeitando somente recursos autorizados. |
| “Faites un graphique des ventes annuelles.” | Reconhece tempo anual e tema de vendas; não exige tabela na primeira mensagem. |
| “Use ventas_anuales e publique no CBMES.” | Prioriza a fonte explicitamente nomeada, valida-a e inclui o dashboard no plano. |
| “Crie um gráfico de margem por ano.” | Descobre candidatos por `margem`/`margin`/`margen`/`marge`; se não houver medida compatível, oferece alternativas ou esclarecimento. |

## Métricas e testes

- Cobrir unitariamente normalização, expansão, ranking, limiar e ambiguidade.
- Cobrir integração com RBAC, RLS, datasets, tabelas e saved queries.
- Cobrir E2E de prompt genérico até aprovação e execução de chart/dashboard.
- Registrar latência de descoberta, quantidade de candidatos, chamadas ao
  Ollama e tokens. O índice/ranking local deve reduzir, e não ampliar, o
  contexto enviado ao modelo.
