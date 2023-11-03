!!! note
    We are going to have more integrations, this is just the beginning!

## ASGI

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

## WSGI

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

[open-telemetry-wsgi-middleware]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html

## Standard Library Logging

Logfire can act as a sink for standard library logging by emitting a Logfire log for every standard library log record.

```py
from logging import basicConfig, getLogger

from logfire.integrations.logging import LogfireLoggingHandler

basicConfig(handlers=[LogfireLoggingHandler()])

logger = getLogger(__name__)

logger.error("{first_name=} failed!", extra={"first_name": "Fred"})
```
