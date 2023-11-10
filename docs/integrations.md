!!! note
    We are going to have more integrations, this is just the beginning!

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

You can also change Logfire Pydantic plugin configuration by using
[plugin_settings](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.plugin_settings) config.

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

## ASGI

??? tip "Installation"
    Install `pip install "logfire[asgi]"` to use this integration.

    The `asgi` extras contains the [`opentelemetry-instrumentation-asgi`][open-telemetry-asgi-middleware] package.

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

You can read more about the OpenTelemetry ASGI middleware [here][open-telemetry-asgi-middleware].

## WSGI

??? tip "Installation"
    Install `pip install "logfire[wsgi]"` to use this integration.

    The `wsgi` extras contains the [`opentelemetry-instrumentation-wsgi`][open-telemetry-wsgi-middleware] package.

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

You can read more about the OpenTelemetry WSGI middleware [here][open-telemetry-wsgi-middleware].


## Standard Library Logging

Logfire can act as a sink for standard library logging by emitting a Logfire log for every standard library log record.

```py
from logging import basicConfig, getLogger

from logfire.integrations.logging import LogfireLoggingHandler

basicConfig(handlers=[LogfireLoggingHandler()])

logger = getLogger(__name__)

logger.error("{first_name=} failed!", extra={"first_name": "Fred"})
```

[open-telemetry-wsgi-middleware]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html
[open-telemetry-asgi-middleware]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
