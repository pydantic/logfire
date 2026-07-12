---
title: "Instrument a WSGI app: see every request your app handles"
description: "Wrap any WSGI app with Logfire and see every request (its status, timing, and any errors) even if your framework has no dedicated integration."
integration: otel
---
# WSGI

If the [WSGI][wsgi] web framework you're using doesn't have a dedicated integration, wrap your app
with [`logfire.instrument_wsgi()`][logfire.Logfire.instrument_wsgi] to see every request it handles
(the status, how long it took, and any errors) as a **trace** (the full journey of one request, made
of nested **spans**, where each span is one unit of work with a name, a start, and a duration) in
Logfire.

WSGI is the standard interface between synchronous Python web servers and apps. If you're on Flask or
Django, prefer their dedicated integrations ([Flask](flask.md), [Django](django.md)), which capture
route details this generic wrapper can't.

## What you'll capture

- Each request as a span, with its HTTP status and duration
- The request method and path
- Any errors raised while handling the request

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `wsgi` extra:

{{ install_logfire(extras=['wsgi']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_wsgi()`][logfire.Logfire.instrument_wsgi], which wraps your app so every request
is recorded. The example below uses the standard library [`wsgiref`][wsgiref] server.

```py title="main.py" hl_lines="5 12" skip-run="true" skip-reason="server-start"
from wsgiref.simple_server import make_server

import logfire

logfire.configure()


def app(env, start_response):
    start_response('200 OK', [('Content-Type', 'text/html')])
    return [b'Hello World']


app = logfire.instrument_wsgi(app)

with make_server('', 8000, app) as httpd:
    # Serve until process is killed
    httpd.serve_forever()
```

Run it with `python main.py`.

## Verify it worked

With the app running, open [http://localhost:8000/](http://localhost:8000/) in your browser.

Then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and go to the **Live**
view. Within a few seconds you should see a span for the request. Click it to see its duration, the
method and path, and the response status.

<!-- TODO(app-verify): screenshot of a WSGI request span in the Live view, showing the method, path, and status -->

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_wsgi()`.** Configure the connection first,
  then wrap the app.
- **You serve the wrapped app.** `instrument_wsgi()` returns a new app object; make sure that's the
  one your server runs.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually sent a request.** Spans appear only after the app is hit; reload the URL above.

## Advanced

### Passing options to the OpenTelemetry instrumentor

The keyword arguments of [`logfire.instrument_wsgi()`][logfire.Logfire.instrument_wsgi] are passed to
the [`OpenTelemetryMiddleware`][opentelemetry.instrumentation.wsgi.OpenTelemetryMiddleware] class of
the OpenTelemetry WSGI Instrumentation package.

## Reference

- API reference: [`logfire.instrument_wsgi()`][logfire.Logfire.instrument_wsgi]
- Underlying OpenTelemetry package:
  [`OpenTelemetryMiddleware`][opentelemetry.instrumentation.wsgi.OpenTelemetryMiddleware]

[wsgi]: https://wsgi.readthedocs.io/en/latest/
[wsgiref]: https://docs.python.org/3/library/wsgiref.html
