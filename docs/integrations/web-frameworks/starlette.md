---
title: "Instrument Starlette: see every request your app handles"
description: "Add a few lines to your Starlette app and see every request in Logfire: the route, timing, the response status, and any errors."
integration: otel
---
# Starlette

See every request your [Starlette][starlette] app handles (the route, how long it took, the response
status, and any errors) as a **trace** (the full journey of one request, made of nested **spans**,
where each span is one unit of work with a name, a start, and a duration) in Logfire.

## What you'll capture

- Each request as a span, with its HTTP status and duration
- The matched route and method
- Any errors raised while handling the request

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `starlette` extra:

{{ install_logfire(extras=['starlette']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_starlette()`][logfire.Logfire.instrument_starlette] to record every request.

To run the example below, also install [Uvicorn][uvicorn], the server that runs the app:

```bash
pip install uvicorn
```

```py title="main.py" hl_lines="7 14" skip-run="true" skip-reason="server-start"
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

import logfire

logfire.configure()


async def home(request: Request) -> PlainTextResponse:
    return PlainTextResponse('Hello, world!')


app = Starlette(routes=[Route('/', home)])
logfire.instrument_starlette(app)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app)
```

Run it with `python main.py`.

## Verify it worked

With the app running, open [http://localhost:8000/](http://localhost:8000/) in your browser.

Then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and go to the **Live**
view. Within a few seconds you should see a span for the request. Click it to see its duration, the
matched route, and the response status.

<!-- TODO(app-verify): screenshot of a Starlette request span in the Live view, showing the matched route and status -->

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_starlette()`.** Configure the connection
  first, then instrument the app.
- **You call `instrument_starlette(app)` exactly once**, on the same `app` object you serve.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually sent a request.** Spans appear only after a route is hit; reload the URL above.

## Advanced

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_starlette()`][logfire.Logfire.instrument_starlette] accepts additional keyword
arguments and passes them to the OpenTelemetry `StarletteInstrumentor.instrument_app()` method. See
[their documentation][opentelemetry-starlette] for the full list.

### Why not the OpenTelemetry ASGI middleware?

If you're a more experienced user, you might wonder why we don't use the
[OpenTelemetry ASGI middleware][opentelemetry-asgi] directly. The reason is that the
`StarletteInstrumentor` wraps that middleware and adds extra information about the matched routes.

### Proxying browser telemetry

If your frontend sends telemetry from the browser, **never expose your Logfire write token in
frontend code**: anyone who loads the page could read it and send data to your project.

Instead, use an experimental proxy handler to forward OpenTelemetry Protocol (OTLP) data (the
standard wire format Logfire uses to receive telemetry) through your Starlette backend, where the
token stays secret. See the
[Logfire JS browser package docs](https://pydantic.dev/docs/logfire/typescript-sdk/packages/browser/#python-backend-proxy)
for setup.

## Reference

- API reference: [`logfire.instrument_starlette()`][logfire.Logfire.instrument_starlette]
- Underlying OpenTelemetry package: [Starlette instrumentation][opentelemetry-starlette]

[starlette]: https://www.starlette.io/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-starlette]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html
[uvicorn]: https://www.uvicorn.org/
