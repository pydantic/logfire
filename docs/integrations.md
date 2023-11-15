You can integrate Logfire with other libraries and frameworks.

## Pydantic

??? tip "Installation"
    Install `pip install "logfire[pydantic]"` to use this integration.

    The `pydantic` optional install group contains the [`pydantic`](https://docs.pydantic.dev/latest/) package.

Pydantic allows users to create [plugins](https://docs.pydantic.dev/latest/concepts/plugins/) that
can be used to extend the functionality of the library.

Logfire has a Pydantic plugin to instrument Pydantic models. The plugin provides logs and metrics
about model validation, and it's disabled by default. You can enable it using the
[`pydantic_plugin_record`](configuration.md) configuration.

You can blacklist or whitelist modules and models by using [`pydantic_plugin_include`](configuration.md)
and [`pydantic_plugin_exclude`](configuration.md) configurations.

You can also change Logfire Pydantic plugin configuration by using [`plugin_settings`][plugin_settings] config.

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'failure'}}):
    ...
```

The `record` config accepts following values:

  * `off`: Disable instrumentation. This is default value.
  * `all`: Send traces and metrics for all events.
  * `failure`: Send metrics for all validations and traces only for validation failures.
  * `metrics`: Send only metrics.


[Sampling](advanced/sampling.md) can be configured by `trace_sample_rate` key in [`plugin_settings`][plugin_settings].

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'all', 'trace_sample_rate': 0.4}}):
    ...
```

Tags can be included by adding the `tags` key in [`plugin_settings`][plugin_settings].

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'all', 'tags': ('tag1', 'tag2')}}):
    ...
```

`tags` value can be one of the following options:

  * List of strings. e.g. `['tag1', 'tag2']`
  * Tuple of strings. e.g. `('tag1', 'tag2')`
  * Comma separated string. e.g. `'tag1,tag2'`

## ASGI

??? tip "Installation"
    Install `pip install "logfire[asgi]"` to use this integration.

    The `asgi` extras contains the [`opentelemetry-instrumentation-asgi`][opentelemetry-asgi] package.

Since Logfire is compliant with the OpenTelemetry specification, you can integrate it with any ASGI framework.

=== "FastAPI"

    ```py
    from fastapi import FastAPI
    from fastapi.middleware import Middleware
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    app = FastAPI(middleware=[Middleware(OpenTelemetryMiddleware)])


    @app.get('/')
    async def home():
        ...
    ```

=== "Quart"

    ```py
    from quart import Quart
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    app = Quart(__name__)
    app.asgi_app = OpenTelemetryMiddleware(app.asgi_app)

    @app.route("/")
    async def hello():
        return "Hello!"

    if __name__ == "__main__":
        app.run(debug=True)
    ```

=== "Django 3.0"

    ```py
    import os
    from django.core.asgi import get_asgi_application
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asgi_example.settings')

    application = get_asgi_application()
    application = OpenTelemetryMiddleware(application)
    ```

=== "Raw ASGI"

    ```py
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    app = ...  # An ASGI application.
    app = OpenTelemetryMiddleware(app)
    ```

You can read more about the OpenTelemetry ASGI middleware [here][opentelemetry-asgi].

## WSGI

??? tip "Installation"
    Install `pip install "logfire[wsgi]"` to use this integration.

    The `wsgi` extras contains the [`opentelemetry-instrumentation-wsgi`][opentelemetry-wsgi] package.

Since Logfire is compliant with the OpenTelemetry specification, you can integrate it with any WSGI framework.

=== "Flask"

    ```py
    from flask import Flask
    from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

    app = Flask(__name__)
    app.wsgi_app = OpenTelemetryMiddleware(app.wsgi_app)

    @app.route("/")
    def hello():
        return "Hello!"

    if __name__ == "__main__":
        app.run(debug=True)
    ```

=== "Django"

    ```py
    import os
    from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
    from django.core.wsgi import get_wsgi_application

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')

    application = get_wsgi_application()
    application = OpenTelemetryMiddleware(application)
    ```

You can read more about the OpenTelemetry WSGI middleware [here][opentelemetry-wsgi].

## HTTPX

??? tip "Installation"
    Install `pip install "logfire[httpx]"` to use this integration.

    The `httpx` extras contains the [`httpx`][httpx] package.

You can use the HTTPX OpenTelemetry package to instrument HTTPX requests.

```py
import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

HTTPXClientInstrumentor().instrument()

with httpx.Client() as client:
    client.get("https://httpbin.org/get")
```

You can read more about the HTTPX OpenTelemetry package [here][opentelemetry-httpx].

## Requests

??? tip "Installation"
    Install `pip install "logfire[requests]"` to use this integration.

    The `requests` extras contains the [`requests`][requests] package.

You can use the requests OpenTelemetry package to instrument [`requests`][requests].

```py
import requests
from opentelemetry.instrumentation.requests import RequestsInstrumentor

RequestsInstrumentor().instrument()

requests.get("https://httpbin.org/get")
```

You can read more about the [`requests`][requests] OpenTelemetry package [here][opentelemetry-requests].

## SQLAlchemy

??? tip "Installation"
    Install `pip install "logfire[sqlalchemy]"` to use this integration.

    The `sqlalchemy` extras contains the [`opentelemetry-instrumentation-sqlalchemy`][opentelemetry-sqlalchemy] package.

You can use the SQLAlchemy OpenTelemetry package to instrument SQLAlchemy.

```py
from sqlalchemy import create_engine

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

engine = create_engine("sqlite:///:memory:")
SQLAlchemyInstrumentor().instrument(engine=engine)
```

You can read more about the SQLAlchemy OpenTelemetry package [here][opentelemetry-sqlalchemy].

## Psycopg2

??? tip "Installation"
    Install `pip install "logfire[psycopg2]"` to use this integration.

    The `psycopg2` extras contains the [`opentelemetry-instrumentation-psycopg2`][opentelemetry-psycopg2] package.

You can use the Psycopg2 OpenTelemetry package to instrument Psycopg2.

```py
import psycopg2
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor


Psycopg2Instrumentor().instrument()

cnx = psycopg2.connect(database='Database')
```

You can read more about the Psycopg2 OpenTelemetry package [here][opentelemetry-psycopg2].

## Mongo

??? tip "Installation"
    Install `pip install "logfire[mongo]"` to use this integration.

    The `mongo` extras contains the [`opentelemetry-instrumentation-pymongo`][opentelemetry-pymongo] package.

You can use the PyMongo OpenTelemetry package to instrument PyMongo.

```py
import pymongo
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor


PymongoInstrumentor().instrument()

client = pymongo.MongoClient()
```

You can read more about the PyMongo OpenTelemetry package [here][opentelemetry-pymongo].

## Standard Library Logging

Logfire can act as a sink for standard library logging by emitting a Logfire log for every standard library log record.

```py
from logging import basicConfig, getLogger

from logfire.integrations.logging import LogfireLoggingHandler

basicConfig(handlers=[LogfireLoggingHandler()])

logger = getLogger(__name__)

logger.error("{first_name=} failed!", extra={"first_name": "Fred"})
```

[opentelemetry-wsgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
[opentelemetry-requests]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
[opentelemetry-sqlalchemy]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
[httpx]: https://www.python-httpx.org/
[requests]: https://docs.python-requests.org/en/master/
[plugin_settings]: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.plugin_settings
