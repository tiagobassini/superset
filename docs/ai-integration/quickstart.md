# AI Integration quickstart

Enable `ENABLE_AI_INTEGRATION=true` in `docker-compose.yml`, restart Superset,
and open **Settings → AI Agents** as an administrator.

For Ollama in the same Compose network use `http://ollama:11434`. Select an
installed model, permitted tools and roles, then use **Test connection** before
saving. Users need `can_use_ai_chat`; administrators need
`can_manage_ai_agents`.

Read tools run immediately. Each write operation requires explicit confirmation.
Superset records executed AI writes and denied AI permissions in its audit logger.
Never put provider API keys in browser configuration.
