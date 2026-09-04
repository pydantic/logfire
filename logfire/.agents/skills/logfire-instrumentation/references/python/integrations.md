# Python Integration Reference

## Web Frameworks

| Framework | Instrumentor | Needs app instance | Extra |
|-----------|-------------|-------------------|-------|
| FastAPI | `logfire.instrument_fastapi(app)` | Yes | `fastapi` |
| Django | `logfire.instrument_django(app)` | Yes | `django` |
| Flask | `logfire.instrument_flask(app)` | Yes | `flask` |
| Starlette | `logfire.instrument_starlette(app)` | Yes | `starlette` |
| Any ASGI app | `logfire.instrument_asgi(app)` | Yes | `asgi` |
| Any WSGI app | `logfire.instrument_wsgi(app)` | Yes | `wsgi` |

## HTTP Clients

| Library | Instrumentor | Extra |
|---------|-------------|-------|
| httpx | `logfire.instrument_httpx()` | `httpx` |
| requests | `logfire.instrument_requests()` | `requests` |
| aiohttp (client) | `logfire.instrument_aiohttp_client()` | `aiohttp` or `aiohttp-client` |
| aiohttp (server) | `logfire.instrument_aiohttp_server()` | `aiohttp-server` |

## Databases

| Library | Instrumentor | Extra |
|---------|-------------|-------|
| asyncpg | `logfire.instrument_asyncpg()` | `asyncpg` |
| psycopg | `logfire.instrument_psycopg()` | `psycopg` |
| psycopg2 | `logfire.instrument_psycopg2()` | `psycopg2` |
| SQLAlchemy | `logfire.instrument_sqlalchemy()` | `sqlalchemy` |
| PyMongo | `logfire.instrument_pymongo()` | `pymongo` |
| MySQL | `logfire.instrument_mysql()` | `mysql` |
| SQLite3 | `logfire.instrument_sqlite3()` | `sqlite3` |
| Redis | `logfire.instrument_redis()` | `redis` |

## AI/LLM Frameworks

PydanticAI, OpenAI, and Anthropic need **no Logfire extra** — install the library itself (`uv add pydantic-ai` / `uv add openai` / `uv add anthropic`); Logfire's own AI extras are `litellm`, `dspy`, and `google-genai`.

| Framework | Instrumentor | Requirement |
|-----------|-------------|-------|
| PydanticAI | `logfire.instrument_pydantic_ai()` | `pydantic-ai` installed (no extra) |
| OpenAI | `logfire.instrument_openai()` | `openai` installed (no extra) |
| OpenAI Agents SDK | `logfire.instrument_openai_agents()` | `agents` (openai-agents-python) installed (no extra) |
| Anthropic | `logfire.instrument_anthropic()` | `anthropic` installed (no extra) |
| Claude Agent SDK | `logfire.instrument_claude_agent_sdk()` | `claude_agent_sdk` installed (no extra) |
| LiteLLM | `logfire.instrument_litellm()` | `litellm` extra |
| DSPy | `logfire.instrument_dspy()` | `dspy` extra |
| Google GenAI | `logfire.instrument_google_genai()` | `google-genai` extra |

```python
import logfire

logfire.configure()
logfire.instrument_pydantic_ai()  # captures agent runs, tool calls, LLM request/response
# or:
logfire.instrument_openai()       # captures chat completions, embeddings, token counts
logfire.instrument_anthropic()    # captures messages, token usage
```

For PydanticAI, each agent run becomes a parent span containing child spans for every tool call and LLM request. See the main skill's Agent Frameworks table for coverage depth across other frameworks (LangChain, CrewAI, AutoGen, ...).

## Task Queues

| Framework | Instrumentor | Extra |
|-----------|-------------|-------|
| Celery | `logfire.instrument_celery()` | `celery` |

## Other

| Feature | Instrumentor | Requirement |
|---------|-------------|-------|
| System Metrics | `logfire.instrument_system_metrics()` | `system-metrics` extra |
| Pydantic model validation | `logfire.instrument_pydantic()` | no extra (distinct from `instrument_pydantic_ai()` above) |
| AWS Lambda | handler wrapper | `aws-lambda` extra |
| SurrealDB | `logfire.instrument_surrealdb()` | no extra |
| MCP (client and server) | `logfire.instrument_mcp()` | no extra |
| `print()` redirection | `logfire.instrument_print()` | no extra |

`gateway`, `datasets`, and `variables` are extras too, but for separate product features, not app instrumentation: the AI Gateway proxy, the evals SDK (see the `logfire-evals` skill), and managed feature flags respectively.

## Gunicorn Configuration

```python
# gunicorn.conf.py
import logfire

def post_fork(server, worker):
    logfire.configure()
    logfire.instrument_fastapi(app)
```
