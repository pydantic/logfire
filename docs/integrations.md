You can integrate Logfire with other libraries and frameworks.

## Pydantic

!!! tip "Installation"
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

## Web Frameworks

You can integrate Logfire with web frameworks using the OpenTelemetry instrumentation packages.

### [FastAPI][fastapi]

!!! tip "Installation"
    Install `pip install "logfire[fastapi]"` to use this integration.

    The `fastapi` extras contains the [`opentelemetry-instrumentation-fastapi`][opentelemetry-fastapi] package.

You can use the FastAPI OpenTelemetry package to instrument FastAPI.

```py
import fastapi
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = fastapi.FastAPI()

@app.get("/foobar")
async def foobar():
    return {"message": "hello world"}

FastAPIInstrumentor.instrument_app(app)
```

You can read more about the FastAPI OpenTelemetry package [here][opentelemetry-fastapi].

### [Flask][flask]

!!! tip "Installation"
    Install `pip install "logfire[flask]"` to use this integration.

    The `flask` extras contains the [`opentelemetry-instrumentation-flask`][opentelemetry-flask] package.

You can use the Flask OpenTelemetry package to instrument Flask.

```py
from flask import Flask
from opentelemetry.instrumentation.flask import FlaskInstrumentor

app = Flask(__name__)

FlaskInstrumentor().instrument_app(app)

@app.route("/")
def hello():
    return "Hello!"

if __name__ == "__main__":
    app.run(debug=True)
```

You can read more about the Flask OpenTelemetry package [here][opentelemetry-flask].

### [Django][django]

!!! tip "Installation"
    Install `pip install "logfire[django]"` to use this integration.

    The `django` extras contains the [`opentelemetry-instrumentation-django`][opentelemetry-django] package.

You can use the Django OpenTelemetry package to instrument Django.

```py
from opentelemetry.instrumentation.django import DjangoInstrumentor

DjangoInstrumentor().instrument()
```

You can read more about the Django OpenTelemetry package [here][opentelemetry-django].

### [ASGI][asgi]

!!! tip "Installation"
    Install `pip install "logfire[asgi]"` to use this integration.

    The `asgi` extras contains the [`opentelemetry-instrumentation-asgi`][opentelemetry-asgi] package.

Since Logfire is compliant with the OpenTelemetry specification, you can integrate it with any [ASGI][asgi] framework.

```py
import uvicorn
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

app = ...

app = OpenTelemetryMiddleware(app)

if __name__ == "__main__":
    uvicorn.run(app)
```

You can read more about the OpenTelemetry ASGI middleware [here][opentelemetry-asgi].

## [WSGI][wsgi]

!!! tip "Installation"
    Install `pip install "logfire[wsgi]"` to use this integration.

    The `wsgi` extras contains the [`opentelemetry-instrumentation-wsgi`][opentelemetry-wsgi] package.

Since Logfire is compliant with the OpenTelemetry specification, you can integrate it with any [WSGI][wsgi] framework.

```py
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

app = ...

app = OpenTelemetryMiddleware(app)
```

You can read more about the OpenTelemetry WSGI middleware [here][opentelemetry-wsgi].

## HTTP Clients

You can integrate Logfire with HTTP clients using the OpenTelemetry instrumentation packages.

###  [HTTPX][httpx]

!!! tip "Installation"
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

### [Requests][requests]

!!! tip "Installation"
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

## Databases

You can integrate Logfire with database packages using the OpenTelemetry instrumentation packages.

### [SQLAlchemy][sqlalchemy]

!!! tip "Installation"
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

### [Psycopg2][psycopg2]

!!! tip "Installation"
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

### [Mongo][mongo]

!!! tip "Installation"
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

## [Standard Library Logging][logging]

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
[opentelemetry-fastapi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
[opentelemetry-flask]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/flask/flask.html
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
[opentelemetry-requests]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
[opentelemetry-sqlalchemy]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
[httpx]: https://www.python-httpx.org/
[requests]: https://docs.python-requests.org/en/master/
[plugin_settings]: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.plugin_settings
[asgi]: https://asgi.readthedocs.io/en/latest/
[wsgi]: https://wsgi.readthedocs.io/en/latest/
[fastapi]: https://fastapi.tiangolo.com/
[flask]: https://flask.palletsprojects.com/en/2.0.x/
[django]: https://www.djangoproject.com/
[sqlalchemy]: https://www.sqlalchemy.org/
[psycopg2]: https://www.psycopg.org/
[mongo]: https://pymongo.readthedocs.io/en/stable/
[logging]: https://docs.python.org/3/library/logging.html
