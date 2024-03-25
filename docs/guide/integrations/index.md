# Integrations

Since **Pydantic Logfire** is [OpenTelemetry][opentelemetry] compatible, it can be used with any OpenTelemetry
instrumentation package. You can find the list of all OpenTelemetry instrumentation packages
[here](https://opentelemetry-python-contrib.readthedocs.io/en/latest/).

Below you can see the list of documented integrations.

If a package you are using is not listed here, please let us know on our [Slack][slack]!

| Package                                | Type                    |
|----------------------------------------|-------------------------|
| [Pydantic](pydantic.md)                | Data Validation         |
| [Standard Library Logging](logging.md) | Logging                 |
| [Structlog](structlog.md)              | Logging                 |
| [FastAPI](fastapi.md)                  | Web Framework           |
| [Django](django.md)                    | Web Framework           |
| [Flask](flask.md)                      | Web Framework           |
| [Starlette](starlette.md)              | Web Framework           |
| [ASGI](asgi.md)                        | Web Framework Interface |
| [WSGI](wsgi.md)                        | Web Framework Interface |
| [HTTPX](httpx.md)                      | HTTP Client             |
| [Requests](requests.md)                | HTTP Client             |
| [AIOHTTP](aiohttp.md)                  | HTTP Client             |
| [SQLAlchemy](sqlalchemy.md)            | Databases               |
| [Psycopg2](psycopg2.md)                | Databases               |
| [PyMongo](pymongo.md)                  | Databases               |
| [Redis](redis.md)                      | Databases               |
| [Celery](celery.md)                    | Task Queue              |


[slack]: https://join.slack.com/t/pydanticlogfire/shared_invite/zt-2b57ljub4-936siSpHANKxoY4dna7qng
[opentelemetry]: https://opentelemetry.io/
