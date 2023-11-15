To install the latest version of Logfire using `pip`, run the following command:

```bash
pip install logfire --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
```

Or if you're using `poetry`:

```bash
poetry source add logfire-source https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
poetry add logfire
```

You can also add it to your project requirements:

```txt title='requirements.txt'
--extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
logfire
```

Or add to `pyproject.toml` if you're using `poetry`:

```toml title='pyproject.toml'
[[tool.poetry.source]]
name = "logfire-source"
url = "https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/"

[tool.poetry.dependencies]
python = "^3.8"
pydantic = "^2.0"
python-dotenv = "^1.0.0"
requests = "^2.31.0"
pytest = "^7.4.2"
logfire = {version = "*", source = "logfire-source"}
```

## Extra Dependencies

You can also install extra dependencies for Logfire. Below is a table of the extras and their dependencies.

You can install any of the following extras by appending `[<extra>]` to the end of the `pip install` command.

```bash
pip install "logfire[<extra>]" --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
```

<!-- Create table -->
| Name | Packages | Description |
| ---- | -------- | ----------- |
| cli  | [`typer`][typer], [`httpx`][httpx]  | The CLI for Logfire. See more about it on the [CLI section](index.md#cli). |
| dash | [`httpx`][httpx] | The dashboard for Logfire. |
| pydantic | [`pydantic`][pydantic] | To use the Pydantic plugin. See more on the [Pydantic integration](integrations.md#pydantic). |
| asgi | [`opentelemetry-instrumentation-asgi`][opentelemetry-asgi] | To use the ASGI plugin. See more on the [ASGI integration](integrations.md#asgi). |
| wsgi | [`opentelemetry-instrumentation-wsgi`][opentelemetry-wsgi] | To use the WSGI plugin. See more on the [WSGI integration](integrations.md#wsgi). |
| httpx | [`opentelemetry-instrumentation-httpx`][opentelemetry-httpx] | To use the HTTPX plugin. See more on the [HTTPX integration](integrations.md#httpx). |
| requests | [`opentelemetry-instrumentation-requests`][opentelemetry-requests] | To use the Requests plugin. See more on the [Requests integration](integrations.md#requests). |
| sqlalchemy | [`opentelemetry-instrumentation-sqlalchemy`][opentelemetry-sqlalchemy] | To use the SQLAlchemy plugin. See more on the [SQLAlchemy integration](integrations.md#sqlalchemy). |
| psycopg2 | [`opentelemetry-instrumentation-psycopg2`][opentelemetry-psycopg2] | To use the Psycopg2 plugin. See more on the [Psycopg2 integration](integrations.md#psycopg2). |
| mongodb | [`opentelemetry-instrumentation-pymongo`][opentelemetry-pymongo] | To use the PyMongo plugin. See more on the [PyMongo integration](integrations.md#pymongo). |
| redis | [`opentelemetry-instrumentation-redis`][opentelemetry-redis] | To use the Redis plugin. See more on the [Redis integration](integrations.md#redis). |

[httpx]: https://www.python-httpx.org/
[typer]: https://typer.tiangolo.com/
[pydantic]: https://pydantic-docs.helpmanual.io/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-wsgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
[opentelemetry-requests]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
[opentelemetry-sqlalchemy]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
[opentelemetry-redis]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html
