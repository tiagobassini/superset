# Validações Pendentes — Integração de IA

As validações unitárias da fase 1.5 são executadas com provedores e cache
simulados. As atividades abaixo exigem infraestrutura ou credenciais que não
devem ser assumidas no ambiente de desenvolvimento.

## Provedores externos

- Executar uma conversa com tool calling contra OpenAI, Anthropic e um endpoint
  OpenAI-compatível (DeepSeek/Codex).
- Pré-requisitos: criar agentes ativos com chaves de API válidas, habilitar
  `ENABLE_AI_INTEGRATION`, aplicar a migration `33c72567c98a` e usar uma conta
  de teste sem dados confidenciais.

## Ollama e cache distribuído

- Executar uma conversa contra um modelo Ollama que suporte tools e validar a
  expiração real de uma `PendingAction` no Redis após 600 segundos.
- Pré-requisitos: Ollama acessível a partir do container Superset, modelo com
  suporte a tool calling instalado, e `CACHE_CONFIG` configurado para Redis.

## Fluxo integrado de escrita

- Confirmar uma ação de SQL Lab, criação/edição de chart, dashboard e dataset
  pela API REST, verificando o registro de auditoria gerado.
- Pré-requisitos: migration aplicada, feature flag habilitada, usuário de teste
  com as permissões `can_use_ai_chat` e `can_ai_*`, database de teste isolado e
  dataset descartável. Não executar contra o banco de desenvolvimento com dados
  compartilhados.

## Endpoints REST de IA

- Executar testes de integração autenticados para chat, confirmação, listagem,
  CRUD e teste de conexão dos agentes em `/api/v1/ai/`.
- Pré-requisitos: migration `33c72567c98a` aplicada no banco de testes,
  `ENABLE_AI_INTEGRATION=True` antes da inicialização da aplicação, usuário de
  teste autenticado com permissões de IA e agentes de teste. O container em
  execução mantém a feature flag desabilitada e informa migrations pendentes,
  portanto esses endpoints não são registrados nem podem ser exercitados sem
  alterar estado compartilhado.
