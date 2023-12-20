You can integrate Logfire with other libraries and frameworks.

<!-- TODO(Marcelo): Add a link on the "let us know". -->
If an important package that you are using is not listed here, please let us know!

## [Pydantic][pydantic]

Pydantic allows users to create [plugins](https://docs.pydantic.dev/latest/concepts/plugins/) that
can be used to extend the functionality of the library.

Logfire has a Pydantic plugin to instrument Pydantic models. The plugin provides logs and metrics
about model validation. The plugin is **disabled** by default. You can enable it using the
[`pydantic_plugin_record`](configuration.md) configuration.

You can blacklist modules and modules by using [`pydantic_plugin_exclude`](configuration.md), and whitelist
using [`pydantic_plugin_include`](configuration.md).

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

The [OpenTelemetry Instrumentation FastAPI][opentelemetry-fastapi] package can be used to instrument FastAPI.

Let's see a minimal example below:

```py
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI()

@app.get("/foobar")
async def foobar():
    return {"message": "hello world"}

FastAPIInstrumentor.instrument_app(app)
```

!!! question "What about the OpenTelemetry ASGI middleware?"
    If you are a more experienced user, you might be wondering why we are not using
    the [OpenTelemetry ASGI middleware][opentelemetry-asgi]. The reason is that the
    `FastAPIInstrumentor` actually wraps the ASGI middleware and adds some additional
    information related to the routes.

### [Flask][flask]

The [OpenTelemetry Instrumentation Flask][opentelemetry-flask] package can be used to instrument Flask.

Let's see a minimal example below:

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

The [OpenTelemetry Instrumentation Django][opentelemetry-django] package can be used to instrument Django.

```py
from opentelemetry.instrumentation.django import DjangoInstrumentor

DjangoInstrumentor().instrument()
```

You can read more about the Django OpenTelemetry package [here][opentelemetry-django].

### [ASGI][asgi]

If the ASGI framework doesn't have a dedicated OpenTelemetry package, you can use the
[OpenTelemetry ASGI middleware][opentelemetry-asgi].

```py
import uvicorn
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

app = ...

app = OpenTelemetryMiddleware(app)

if __name__ == "__main__":
    uvicorn.run(app)
```

You can read more about the OpenTelemetry ASGI middleware [here][opentelemetry-asgi].

### [WSGI][wsgi]

The analogous applies to WSGI. If the WSGI framework doesn't have a dedicated OpenTelemetry
package, you can use the [OpenTelemetry WSGI middleware][opentelemetry-wsgi].

```py
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

app = ...

app = OpenTelemetryMiddleware(app)
```

You can read more about the OpenTelemetry WSGI middleware [here][opentelemetry-wsgi].

## HTTP Clients

You can integrate Logfire with HTTP clients using the OpenTelemetry instrumentation packages.

###  [HTTPX][httpx]

The [OpenTelemetry Instrumentation HTTPX][opentelemetry-httpx] package can be used to instrument HTTPX.

```py
import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

HTTPXClientInstrumentor().instrument()

with httpx.Client() as client:
    client.get("https://httpbin.org/get")
```

You can read more about the HTTPX OpenTelemetry package [here][opentelemetry-httpx].

### [Requests][requests]

The [OpenTelemetry Instrumentation Requests][opentelemetry-requests] package can be used to instrument Requests.

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

The [OpenTelemetry Instrumentation SQLAlchemy][opentelemetry-sqlalchemy] package can be used to instrument SQLAlchemy.

```py
from sqlalchemy import create_engine

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

engine = create_engine("sqlite:///:memory:")
SQLAlchemyInstrumentor().instrument(engine=engine)
```

You can read more about the SQLAlchemy OpenTelemetry package [here][opentelemetry-sqlalchemy].

### [Psycopg2][psycopg2]

The [OpenTelemetry Instrumentation Psycopg2][opentelemetry-psycopg2] package can be used to instrument Psycopg2.

```py
import psycopg2
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor


Psycopg2Instrumentor().instrument()

cnx = psycopg2.connect(database='Database')
```

You can read more about the Psycopg2 OpenTelemetry package [here][opentelemetry-psycopg2].

### [PyMongo][mongo]

The [OpenTelemetry Instrumentation PyMongo][opentelemetry-pymongo] package can be used to instrument PyMongo.

Let's see a minimal example below:

```py
import logfire
from pymongo import MongoClient
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

logfire.info("Instrumenting PyMongo!")

PymongoInstrumentor().instrument()

client = MongoClient()
db = client["test-database"]
collection = db["test-collection"]
collection.insert_one({"name": "MongoDB"})
collection.find_one()
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
[pydantic]: https://docs.pydantic.dev/latest/
