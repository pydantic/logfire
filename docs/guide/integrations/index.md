# Integrations

Since **Pydantic Logfire** is [OpenTelemetry][opentelemetry] compatible, it can be used with any OpenTelemetry
instrumentation package. You can find the list of all OpenTelemetry instrumentation packages
[here](https://opentelemetry-python-contrib.readthedocs.io/en/latest/).

Below you can see the list of documented integrations.

If a package you are using is not listed here, please let us know on our [Slack][slack]!

## Web Frameworks

| Package      |
|--------------|
| [FastAPI](fastapi.md)         |
| [Starlette](starlette.md)     |
| [Django](django.md)           |
| [Flask](flask.md)             |
| [ASGI](asgi.md)               |
| [WSGI](wsgi.md)               |

## HTTP Clients

| Package      |
|--------------|
| [HTTPX](httpx.md)             |
| [Requests](requests.md)       |
| [AIOHTTP](aiohttp.md)         |

## Databases

| Package      |
|--------------|
| [SQLAlchemy](sqlalchemy.md)   |
| [PyMongo](pymongo.md)         |
| [Psycopg2](psycopg2.md)       |
| [Redis](redis.md)             |

## Logging

| Package      |
|--------------|
| [Standard Library Logging](logging.md) |

## Miscellaneous

| Package      |
|--------------|
| [Pydantic](pydantic.md)       |
| [Celery](celery.md)           |

[slack]: https://join.slack.com/t/pydanticlogfire/shared_invite/zt-2b57ljub4-936siSpHANKxoY4dna7qng
[opentelemetry]: https://opentelemetry.io/
