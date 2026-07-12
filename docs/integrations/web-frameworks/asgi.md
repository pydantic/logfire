---
title: "Instrument an ASGI app: see every request your app handles"
description: "Wrap any ASGI app with Logfire and see every request (its status, timing, and any errors) even if your framework has no dedicated integration."
integration: otel
---
# ASGI

If the [ASGI][asgi] web framework you're using doesn't have a dedicated integration, wrap your app
with [`logfire.instrument_asgi()`][logfire.Logfire.instrument_asgi] to see every request it handles
(the status, how long it took, and any errors) as a **trace** (the full journey of one request, made
of nested **spans**, where each span is one unit of work with a name, a start, and a duration) in
Logfire.

ASGI is the standard interface between async Python web servers and apps. If you're on Starlette or
FastAPI, prefer their dedicated integrations ([Starlette](starlette.md), [FastAPI](fastapi.md)), which
capture route details this generic wrapper can't.

## What you'll capture

- Each request as a span, with its HTTP status and duration
- The request method and path
- Any errors raised while handling the request

{{ before_you_start() }}

## Installation

Install `logfire` with the `asgi` extra:

{{ install_logfire(extras=['asgi']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_asgi()`][logfire.Logfire.instrument_asgi], which wraps your app so every request
is recorded.

To run the example below, also install [Uvicorn][uvicorn], the server that runs the app:

```bash
pip install uvicorn
```

```py title="main.py" hl_lines="3 16" skip-run="true" skip-reason="server-start"
import logfire

logfire.configure()


async def app(scope, receive, send):
    assert scope['type'] == 'http'
    await send(
        {
            'type': 'http.response.start',
            'status': 200,
            'headers': [(b'content-type', b'text/plain'), (b'content-length', b'13')],
        }
    )
    await send({'type': 'http.response.body', 'body': b'Hello, world!'})


app = logfire.instrument_asgi(app)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app)
```

Run it with `python main.py`.

## Verify it worked

With the app running, open [http://localhost:8000/](http://localhost:8000/) in your browser.

Then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and go to the **Live**
view. Within a few seconds you should see a span for the request. Click it to see its duration, the
method and path, and the response status.

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_asgi()`.** Configure the connection first,
  then wrap the app.
- **You serve the wrapped app.** `instrument_asgi()` returns a new app object; make sure that's the
  one your server runs.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually sent a request.** Spans appear only after the app is hit; reload the URL above.

## Advanced

### Passing options to the OpenTelemetry instrumentor

The keyword arguments of [`logfire.instrument_asgi()`][logfire.Logfire.instrument_asgi] are passed to
the [`OpenTelemetryMiddleware`][opentelemetry.instrumentation.asgi.OpenTelemetryMiddleware] class of
the OpenTelemetry ASGI Instrumentation package.

## Reference

- API reference: [`logfire.instrument_asgi()`][logfire.Logfire.instrument_asgi]
- Underlying OpenTelemetry package:
  [`OpenTelemetryMiddleware`][opentelemetry.instrumentation.asgi.OpenTelemetryMiddleware]

[asgi]: https://asgi.readthedocs.io/en/latest/
[uvicorn]: https://www.uvicorn.org/
