!!! note
    We are going to have more integrations, this is just the beginning!

    <!-- TODO: Add link to open issue. -->
    If you are an open source maintainer, and want to have an integration with Logfire, please [open an issue]().

## ASGI

!!! info
    You need to install the `logfire[asgi]` extra to use this integration.

    ```bash
    pip install 'logfire[asgi]' --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    ```

Integration with ASGI frameworks like [FastAPI][fastapi], [Starlette][starlette], [Quart][quart], etc.

You just need to add the `LogfireMiddleware` to your application. Let's see an example with [FastAPI][fastapi]:

```py
from fastapi import FastAPI
from logfire.integrations.asgi import LogfireMiddleware

app = FastAPI()
app.add_middleware(LogfireMiddleware)
```

## WSGI

!!! info
    You need to install the `logfire[wsgi]` extra to use this integration.

    ```bash
    pip install 'logfire[wsgi]' --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    ```

Integration with WSGI frameworks like [Flask][flask], [Django][django], etc.

You just need to add the `LogfireMiddleware` to your application. Let's see an example with [Flask][flask]:

```py
from flask import Flask
from logfire.integrations.wsgi import LogfireMiddleware

app = Flask(__name__)
app.wsgi_app = LogfireMiddleware(app.wsgi_app)
```

[fastapi]: https://fastapi.tiangolo.com/
[starlette]: https://www.starlette.io/
[quart]: https://pgjones.gitlab.io/quart/
[flask]: https://flask.palletsprojects.com/en/2.0.x/
[django]: https://www.djangoproject.com/
