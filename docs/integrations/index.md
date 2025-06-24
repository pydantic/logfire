# Integrations

**Pydantic Logfire** supports first-class integration with many popular Python packages using a single `logfire.instrument_<package>()`
function call. Each of these should be called exactly once after [`logfire.configure()`][logfire.configure].

For example, to instrument FastAPI and HTTPX, you would do:

```python
import logfire

logfire.configure()
logfire.instrument_fastapi()
logfire.instrument_httpx()

# ... your application code here ...
```

If a package you are using is not listed in this documentation, please let us know on our [Slack][slack]!

## Documented Integrations

**Logfire** has documented integrations with many technologies, including:

- *LLM Clients and AI Frameworks*: PydanticAI, OpenAI, Anthropic, LangChain, LlamaIndex, Mirascope, LiteLLM, Magentic
- *Web Frameworks*: FastAPI, Django, Flask, Starlette, AIOHTTP, ASGI, WSGI
- *Database Clients*: Psycopg, SQLAlchemy, Asyncpg, PyMongo, MySQL, SQLite3, Redis, BigQuery
- *HTTP Clients*: HTTPX, Requests, AIOHTTP
- *Task Queues and Schedulers*: Airflow, FastStream, Celery
- *Logging Libraries*: Standard Library Logging, Loguru, Structlog
- and more, such as Stripe, AWS Lambda, and system metrics.

The below table lists these integrations and any corresponding `logfire.instrument_<package>()` calls:

| Package                                  | Type                    | Logfire Instrument Call / Notes                                  |
|-------------------------------------------|-------------------------|------------------------------------------------------------------|
| [AIOHTTP](http-clients/aiohttp.md)        | HTTP Client             | [`logfire.instrument_aiohttp_client()`,][logfire.Logfire.instrument_aiohttp_client] [`logfire.instrument_aiohttp_server()`][logfire.Logfire.instrument_aiohttp_server] |
| [Airflow](event-streams/airflow.md)       | Task Scheduler          | N/A (built in, config needed)                                    |
| [Anthropic](llms/anthropic.md)            | AI                      | [`logfire.instrument_anthropic()`][logfire.Logfire.instrument_anthropic]                                 |
| [ASGI](web-frameworks/asgi.md)            | Web Framework Interface | [`logfire.instrument_asgi()`][logfire.Logfire.instrument_asgi]                                      |
| [AWS Lambda](aws-lambda.md)               | Cloud Function          | [`logfire.instrument_aws_lambda()`][logfire.Logfire.instrument_aws_lambda]                                |
| [Asyncpg](databases/asyncpg.md)           | Database                | [`logfire.instrument_asyncpg()`][logfire.Logfire.instrument_asyncpg]                                   |
| [BigQuery](databases/bigquery.md)         | Database                | N/A (built in, no config needed)                                 |
| [Celery](event-streams/celery.md)         | Task Queue              | [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery]                                    |
| [Django](web-frameworks/django.md)        | Web Framework           | [`logfire.instrument_django()`][logfire.Logfire.instrument_django]                                    |
| [FastAPI](web-frameworks/fastapi.md)      | Web Framework           | [`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi]                                   |
| [FastStream](event-streams/faststream.md) | Task Queue              | N/A (built in, config needed)                                    |
| [Flask](web-frameworks/flask.md)          | Web Framework           | [`logfire.instrument_flask()`][logfire.Logfire.instrument_flask]                                     |
| [HTTPX](http-clients/httpx.md)            | HTTP Client             | [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx]                                     |
| [LangChain](llms/langchain.md)            | AI Framework            | N/A (built-in OpenTelemetry support)                             |
| [LlamaIndex](llms/llamaindex.md)          | AI Framework            | N/A (requires LlamaIndex OTel package)                           |
| [LiteLLM](llms/litellm.md)                | AI Gateway              | N/A (requires LiteLLM callback setup)                            |
| [Loguru](loguru.md)                       | Logging                 | See documentation                                                |
| [Magentic](llms/magentic.md)              | AI Framework            | N/A (built-in Logfire support)                                   |
| [Mirascope](llms/mirascope.md)            | AI Framework            | N/A (use mirascope `@with_logfire` decorator)                    |
| [MySQL](databases/mysql.md)               | Database                | [`logfire.instrument_mysql()`][logfire.Logfire.instrument_mysql]                                     |
| [OpenAI](llms/openai.md)                  | AI                      | [`logfire.instrument_openai()`][logfire.Logfire.instrument_openai]                                    |
| [Psycopg](databases/psycopg.md)           | Database                | [`logfire.instrument_psycopg()`][logfire.Logfire.instrument_psycopg]                                   |
| [Pydantic](pydantic.md)                   | Data Validation         | [`logfire.instrument_pydantic()`][logfire.Logfire.instrument_pydantic]                                  |
| [PydanticAI](llms/pydanticai.md)          | AI                      | [`logfire.instrument_pydantic_ai()`][logfire.Logfire.instrument_pydantic_ai]                               |
| [PyMongo](databases/pymongo.md)           | Database                | [`logfire.instrument_pymongo()`][logfire.Logfire.instrument_pymongo]                                   |
| [Redis](databases/redis.md)               | Database                | [`logfire.instrument_redis()`][logfire.Logfire.instrument_redis]                                     |
| [Requests](http-clients/requests.md)      | HTTP Client             | [`logfire.instrument_requests()`][logfire.Logfire.instrument_requests]                                  |
| [SQLAlchemy](databases/sqlalchemy.md)     | Database                | [`logfire.instrument_sqlalchemy()`][logfire.Logfire.instrument_sqlalchemy]                                |
| [SQLite3](databases/sqlite3.md)           | Database                | [`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3]                                   |
| [Standard Library Logging](logging.md)    | Logging                 | See documentation                                                |
| [Starlette](web-frameworks/starlette.md)  | Web Framework           | [`logfire.instrument_starlette()`][logfire.Logfire.instrument_starlette]                                 |
| [Stripe](stripe.md)                       | Payment Gateway         | N/A (requires other instrumentations)                            |
| [Structlog](structlog.md)                 | Logging                 | See documentation                                                |
| [System Metrics](system-metrics.md)       | System Metrics          | [`logfire.instrument_system_metrics()`][logfire.Logfire.instrument_system_metrics]                            |
| [WSGI](web-frameworks/wsgi.md)            | Web Framework Interface | [`logfire.instrument_wsgi()`][logfire.Logfire.instrument_wsgi]                                      |

If you are using Logfire with a web application, we also recommend reviewing
our [Web Frameworks](web-frameworks/index.md)
documentation.

## OpenTelemetry Integrations

Since **Logfire** is [OpenTelemetry][opentelemetry] compatible, it can be used with any OpenTelemetry
instrumentation package. You can find the list of all OpenTelemetry instrumentation packages
[here](https://opentelemetry-python-contrib.readthedocs.io/en/latest/).

Many of the integrations documented in the previous section are based upon the OpenTelemetry instrumentation packages
with first-class support built into **Logfire**.

## Creating Custom Integrations

If you are a maintainer of a package and would like to create an integration for **Logfire**, you can do it! :smile:

We've created a shim package called `logfire-api`, which can be used to integrate your package with **Logfire**.

The idea of `logfire-api` is that it doesn't have any dependencies. It's a very small package that matches the API of **Logfire**.
We created it so that you can create an integration for **Logfire** without having to install **Logfire** itself.

You can use `logfire-api` as a lightweight dependency of your own package.
If `logfire` is installed, then `logfire-api` will use it. If not, it will use a no-op implementation.
This way users of your package can decide whether or not they want to install `logfire`, and you don't need to
check whether or not it's installed.

Here's how you can use `logfire-api`:

```python
import logfire_api as logfire

logfire.info("Hello, Logfire!")
```

!!! note
    You generally *don't* want to call `logfire_api.configure()`, it's up to your users to call
    `logfire.configure()` if they want to use the integration.

All the **Logfire** API methods are available in `logfire-api`.

[slack]: https://logfire.pydantic.dev/docs/join-slack/
[opentelemetry]: https://opentelemetry.io/
