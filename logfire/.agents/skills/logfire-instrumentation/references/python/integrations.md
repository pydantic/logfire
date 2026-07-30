# Python Integration Reference

## Web Frameworks

| Framework | Instrumentor | Needs app instance | Extra |
|-----------|-------------|-------------------|-------|
| FastAPI | `logfire.instrument_fastapi(app)` | Yes | `fastapi` |
| Django | `logfire.instrument_django(app)` | Yes | `django` |
| Flask | `logfire.instrument_flask(app)` | Yes | `flask` |
| Starlette | `logfire.instrument_starlette(app)` | Yes | `starlette` |
| AIOHTTP | `logfire.instrument_aiohttp_client()` | No | `aiohttp` |

## HTTP Clients

| Library | Instrumentor | Extra |
|---------|-------------|-------|
| httpx | `logfire.instrument_httpx()` | `httpx` |
| requests | `logfire.instrument_requests()` | `requests` |

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

| Framework | Instrumentor | Extra |
|-----------|-------------|-------|
| PydanticAI | `logfire.instrument_pydantic_ai()` | `pydantic-ai` |
| OpenAI | `logfire.instrument_openai()` | `openai` |
| Anthropic | `logfire.instrument_anthropic()` | `anthropic` |
| LiteLLM | `logfire.instrument_litellm()` | `litellm` |
| DSPy | `logfire.instrument_dspy()` | `dspy` |
| Google GenAI | `logfire.instrument_google_genai()` | `google-genai` |

## Task Queues

| Framework | Instrumentor | Extra |
|-----------|-------------|-------|
| Celery | `logfire.instrument_celery()` | `celery` |

## Other

| Feature | Instrumentor | Extra |
|---------|-------------|-------|
| System Metrics | `logfire.instrument_system_metrics()` | `system-metrics` |
| Pydantic Models | `logfire.instrument_pydantic()` | - (built-in) |
| AWS Lambda | handler wrapper | `aws-lambda` |

## Gunicorn Configuration

```python
# gunicorn.conf.py
import logfire

def post_fork(server, worker):
    logfire.configure()
    logfire.instrument_fastapi(app)
```
