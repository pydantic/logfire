---
title: "Configure Logfire with Gunicorn"
description: "Set up Logfire in Gunicorn's worker hooks so each worker process sends data correctly under its pre-fork worker model."
integration: otel
---
# Gunicorn

See every request your app handles when it runs under [Gunicorn](https://docs.gunicorn.org/en/latest/index.html),
across all of Gunicorn's worker processes, as **spans** (each span is one unit of work with a name, a
start, and a duration) in Logfire.

Gunicorn is a Python web server that runs your app in several worker processes at once, forking a fresh
process for each. Because those workers are created *after* Gunicorn starts, Logfire has to be set up
inside each worker rather than once at startup. This page shows where.

## What you'll capture

- Each request as a span, no matter which worker process handled it
- The duration and status of every request across all workers
- Any errors raised while handling a request

{{ before_you_start() }}

## Installation

Install `logfire`:

{{ install_logfire() }}

If you also want to instrument the web framework you run under Gunicorn (Flask, for example), install
its extra too. See that framework's [integration page](../index.md).

## Usage

Call `logfire.configure()` in Gunicorn's
[`post_fork` hook](https://docs.gunicorn.org/en/latest/settings.html#post-fork) (the function Gunicorn
runs in each worker process right after it forks) so every worker sends data:

```py title="gunicorn_config.py"
import logfire


def post_fork(server, worker):
    logfire.configure()
```

Then start Gunicorn with that configuration file, where `myapp:app` is your WSGI application:

```bash
gunicorn myapp:app --config gunicorn_config.py
```

## Verify it worked

Start Gunicorn and open one of your pages in the browser. Then open the
[Live view](../../guides/web-ui/live.md). Within a few seconds you'll see a span for the request,
regardless of which worker handled it.

## Troubleshooting

Not seeing your requests in Logfire? Check that `logfire.configure()` is called inside the `post_fork`
hook (not at module top level, where it runs before workers fork), and that your write token is set. For
Flask, check that `instrument_flask(worker.wsgi)` runs inside `post_worker_init`, as shown below. Other
frameworks can require different setup; choose the relevant framework from the
[web framework integrations](index.md).

## Advanced

### Instrumenting a Flask application

Here you also instrument a Flask app running under Gunicorn, so each request becomes a span.

The Flask application (`myapp.py`):

```py title="myapp.py"
from flask import Flask

app = Flask(__name__)


@app.route('/')
def index():
    return 'Hello from Flask + Gunicorn!'
```

Configure Logfire after each worker is forked, then instrument the application after Gunicorn loads it
(`gunicorn_config.py`):

```py title="gunicorn_config.py" skip-run="true" skip-reason="server-start"
import logfire


def post_fork(server, worker):
    logfire.configure()


def post_worker_init(worker):
    logfire.instrument_flask(worker.wsgi)
```

Then start Gunicorn:

```bash
gunicorn myapp:app --config gunicorn_config.py
```

Logfire now records a span for every request the Flask app handles, in every worker.

## Reference

- [Gunicorn server hooks](https://docs.gunicorn.org/en/latest/settings.html#server-hooks): where
  configuration and application instrumentation run.
- [`logfire.instrument_flask()`][logfire.Logfire.instrument_flask]: to instrument a Flask app, as
  shown above.
