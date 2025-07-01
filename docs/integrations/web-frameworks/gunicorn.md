---
integration: otel
---

# Gunicorn

[Gunicorn](https://docs.gunicorn.org/en/latest/index.html) is a Python WSGI HTTP server for UNIX.
It is a pre-fork worker model, which means it forks multiple worker processes to handle requests concurrently.

To configure Logfire with Gunicorn, you can use the `logfire.configure()` function to set up Logfire in the
[`post_fork` hook](https://docs.gunicorn.org/en/latest/settings.html#post-fork) in Gunicorn's configuration file:

```py
import logfire

def post_fork(server, worker):
    logfire.configure()
```

Then start Gunicorn with the configuration file:

```bash
gunicorn myapp:app --config gunicorn_config.py
```

Where `myapp:app` is your WSGI application and `gunicorn_config.py` is the configuration file where you defined the `post_fork` function.

## Instrumenting a Flask application

This section shows how to instrument a Flask application running under Gunicorn with Logfire.

Here is the `Flask` application code (`myapp.py`):

```py title="myapp.py"
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from Flask + Gunicorn!"
```

To instrument this Flask application with Logfire, you can modify the `post_fork` function in your Gunicorn configuration file to import and instrument the Flask app (`gunicorn_config.py`):

```py title="gunicorn_config.py"
import logfire

from myapp import app

def post_fork(server, worker):
    logfire.configure()
    logfire.instrument_flask(app)
```

Then, you can start Gunicorn with the following command:

```bash
gunicorn myapp:app --config gunicorn_config.py
```

This will start Gunicorn with the Flask application, and Logfire will automatically instrument the HTTP requests handled by the Flask app.
