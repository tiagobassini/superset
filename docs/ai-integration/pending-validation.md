# Validações Pendentes — Integração de IA

## Frontend Core — Fase 2

A Fase 2 possui fundação funcional (slice Redux, persistência de sessão,
contexto por URL, carregamento de agentes e chamadas HTTP), porém **não está
concluída**. Os seguintes itens precisam de implementação e testes:

- Corrigir a obtenção do título de dashboard e da aba ativa do SQL Lab no
  `useAIContext`; cobrir os quatro contextos com testes que usem o Redux real.
- Testar `useAIChat` e implementar loading por mensagem, tratamento visível de
  falhas e o fluxo completo de confirmar/cancelar ações pendentes.
- Completar os componentes: bolhas distintas para usuário/assistente,
  confirmação integrada às mensagens, scroll automático, botão flutuante,
  minimizar, e componentes/tema padrão do Superset.
- Ajustar a integração no layout: sidebar com largura definida, reserva de
  espaço à direita enquanto aberta e comportamento responsivo sem sobrepor o
  conteúdo.
- Implementar acessibilidade restante: Escape para fechar, foco no campo de
  mensagem ao abrir e testes de teclado/foco/aria.
- Criar testes unitários dos componentes e de integração do painel.

Pré-requisitos para validar o fluxo ponta a ponta: frontend recompilado no
container `superset-node`, `ENABLE_AI_INTEGRATION=True` antes do bootstrap,
database migrado e pelo menos um agente ativo e autorizado. Esses requisitos
não foram alterados durante a auditoria para não modificar o ambiente
compartilhado.

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
