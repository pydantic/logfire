# Integrations

If a package you are using is not listed here, please let us know on our [Slack][slack]!

## OpenTelemetry Integrations

Since **Pydantic Logfire** is [OpenTelemetry][opentelemetry] compatible, it can be used with any OpenTelemetry
instrumentation package. You can find the list of all OpenTelemetry instrumentation packages
[here](https://opentelemetry-python-contrib.readthedocs.io/en/latest/).

Below you can see more details on how to use Logfire with some of the most popular Python packages.

| Package                                  | Type                    |
|------------------------------------------|-------------------------|
| [FastAPI](web-frameworks/fastapi.md)     | Web Framework           |
| [Django](web-frameworks/django.md)       | Web Framework           |
| [Flask](web-frameworks/flask.md)         | Web Framework           |
| [Starlette](web-frameworks/starlette.md) | Web Framework           |
| [ASGI](web-frameworks/asgi.md)           | Web Framework Interface |
| [WSGI](web-frameworks/wsgi.md)           | Web Framework Interface |
| [HTTPX](http-clients/httpx.md)           | HTTP Client             |
| [Requests](http-clients/requests.md)     | HTTP Client             |
| [AIOHTTP](http-clients/aiohttp.md)       | HTTP Client             |
| [SQLAlchemy](databases/sqlalchemy.md)    | Databases               |
| [Asyncpg](databases/asyncpg.md)          | Databases               |
| [Psycopg](databases/psycopg.md)          | Databases               |
| [PyMongo](databases/pymongo.md)          | Databases               |
| [MySQL](databases/mysql.md)              | Databases               |
| [SQLite3](databases/sqlite3.md)          | Databases               |
| [Redis](databases/redis.md)              | Databases               |
| [BigQuery](databases/bigquery.md)        | Databases               |
| [Airflow](event-streams/airflow.md)      | Task Scheduler          |
| [FastStream](event-streams/faststream.md)| Task Queue              |
| [Celery](event-streams/celery.md)        | Task Queue              |
| [Stripe](stripe.md)                      | Payment Gateway         |
| [System Metrics](system-metrics.md)      | System Metrics          |

If you are using Logfire with a web application, we also recommend reviewing
our [Web Frameworks](web-frameworks/index.md)
documentation.

## Custom Integrations

We have special integration with the Pydantic library and the OpenAI SDK:

| Package                        | Type            |
|--------------------------------|-----------------|
| [Pydantic](pydantic.md)        | Data Validation |
| [OpenAI](llms/openai.md)       | AI              |
| [Anthropic](llms/anthropic.md) | AI              |

## Logging Integrations

Finally, we also have documentation for how to use Logfire with existing logging libraries:

| Package                                | Type    |
|----------------------------------------|---------|
| [Standard Library Logging](logging.md) | Logging |
| [Loguru](loguru.md)                    | Logging |
| [Structlog](structlog.md)              | Logging |

[slack]: https://join.slack.com/t/pydanticlogfire/shared_invite/zt-2war8jrjq-w_nWG6ZX7Zm~gnzY7cXSog
[opentelemetry]: https://opentelemetry.io/

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
