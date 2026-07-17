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

## Starting Ollama with AI profile

```bash
docker compose --profile ai up -d ollama ollama-pull
```

## Test Suite Setup and Execution

The AI test suite is defined in `docs/ai-integration/example-database-ai-prompts.md` 
and includes 400+ test cases (P01-P500) organized by purpose:
- **P01–P100**: Original baseline tests
- **P101–P130**: Dashboard creation tests
- **P131–P200**: Theme/topic search tests (read-only)
- **P201–P300**: Chart types and dashboard integration
- **P351–P500**: Direct chat queries (read-only)

### Step 1: Copy scripts to container

```bash
# Copy test runner
docker cp scripts/ai/run_example_prompt_suite.py superset-superset-1:/app/scripts/ai/

# Copy result summarizer
docker cp scripts/ai/summarize_prompt_results.py superset-superset-1:/app/scripts/ai/

# Copy or update prompts file
docker cp docs/ai-integration/example-database-ai-prompts.md superset-superset-1:/app/docs/ai-integration/
```

### Step 2: Run the test suite

**Option A: All tests (P01–P500, ~10-15 minutes depending on model)**

```bash
docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/run_example_prompt_suite.py --output /tmp/ai_prompt_suite.jsonl'
```

**Option B: Specific test groups**

Dashboard creation tests (P101–P130):
```bash
docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/run_example_prompt_suite.py --only P101 P102 P103 P104 P105 --output /tmp/results_dashboards.jsonl'
```

Chart visualization tests (P201–P300):
```bash
docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/run_example_prompt_suite.py --only P201 P202 P203 P204 P205 --output /tmp/results_charts.jsonl'
```

Read-only chat queries (P351–P500):
```bash
docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/run_example_prompt_suite.py --only P351 P352 P353 --output /tmp/results_queries.jsonl'
```

**Option C: Quick test with fail-fast**

Run first 10 cases, stop on first failure:
```bash
docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/run_example_prompt_suite.py --only P01 P02 P03 P04 P05 P06 P07 P08 P09 P10 --fail-fast --output /tmp/quick_test.jsonl'
```

### Step 3: Analyze results

After tests complete, summarize results:

```bash
docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/summarize_prompt_results.py --input /tmp/ai_prompt_suite.jsonl --output /tmp/ai_prompt_suite_resume.jsonl'
```

Copy summary to host:
```bash
docker cp superset-superset-1:/tmp/ai_prompt_suite_resume.jsonl ./ai_prompt_suite_resume.jsonl
```

View summary statistics:
```bash
python3 -c "
import json
with open('./ai_prompt_suite_resume.jsonl', 'r') as f:
    data = json.load(f)
    print('SUMMARY:', json.dumps(data['summary'], indent=2))
    print('ROOT CAUSES:', json.dumps(data['failure_root_causes'], indent=2))
    print('SAMPLE FAILURES:', json.dumps(data['failures_detail'][:3], indent=2))
"
```



## Development Utilities

Interactive shell in container:
```bash
docker exec -it superset-superset-1 bash
```

View container logs:
```bash
docker logs superset-superset-1 -f --tail=100
```

Access Superset UI:
```
http://localhost:8088
```


docker cp scripts/ai/summarize_prompt_results.py superset-superset-1:/app/scripts/ai/summarize_prompt_results.py

docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/summarize_prompt_results.py --input /tmp/ai_prompt_suite.jsonl --output /tmp/ai_prompt_suite_resume.jsonl'


docker cp superset-superset-1:/tmp/ai_prompt_suite.jsonl ./ai_prompt_suite.jsonl

docker cp superset-superset-1:/tmp/ai_prompt_suite_resume.jsonl ./ai_prompt_suite_resume.jsonl

docker cp ./ai_prompt_suite.jsonl superset-superset-1:/tmp/ai_prompt_suite.jsonl 

docker cp superset-superset-1:/tmp/ai_prompt_suite_resume.jsonl /tmp/ai_prompt_suite_resume.jsonl && wc -l /tmp/ai_prompt_suite_resume.jsonl && ls -lh /tmp/ai_prompt_suite_resume.jsonl

python3 -c "import json; data = json.load(open('/tmp/ai_prompt_suite_resume.jsonl')); print(json.dumps({'summary': data['summary'], 'failure_breakdown': data['failure_breakdown'], 'root_causes': data['failure_root_causes']}, indent=2))"


## executando os testes de forma encadeada

docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/run_example_prompt_suite.py --output /tmp/ai_prompt_suite_500.jsonl' && docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/summarize_prompt_results.py --input /tmp/ai_prompt_suite_500.jsonl --output /tmp/results_500_resume.jsonl' && docker cp superset-superset-1:/tmp/results_500_resume.jsonl ./results_500_resume.jsonl


## Cleanup

Remove all AI test artifacts (dashboards, charts, datasets with prefix `AI_TEST_*`):

```bash
docker exec superset-superset-1 bash -lc 'cd /app && .venv/bin/python scripts/ai/cleanup_ai_test_artifacts.py'
```