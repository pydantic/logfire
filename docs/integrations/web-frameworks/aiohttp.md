---
title: "Instrument an AIOHTTP server: see every request your app handles"
description: "Add a few lines to your AIOHTTP server and see every request in Logfire: the path, timing, the response status, and any errors."
integration: otel
---
# AIOHTTP Server

See every request your [AIOHTTP][aiohttp] server handles (the path, how long it took, the response
status, and any errors) as a **trace** (the full journey of one request, made of nested **spans**,
where each span is one unit of work with a name, a start, and a duration) in Logfire.

AIOHTTP is an asynchronous HTTP client and server framework for asyncio. This page covers the
**server** side. For the client side, see [AIOHTTP client](../http-clients/aiohttp.md).

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

Install `logfire` with the `aiohttp-server` extra:

{{ install_logfire(extras=['aiohttp-server']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_aiohttp_server()`][logfire.Logfire.instrument_aiohttp_server] to record every
request.

```py title="server.py" hl_lines="5-6" skip-run="true" skip-reason="server-start"
from aiohttp import web

import logfire

logfire.configure()
logfire.instrument_aiohttp_server()


async def hello(request):
    return web.Response(text='Hello, World!')


async def user_handler(request):
    user_id = request.match_info['user_id']
    return web.json_response({'user_id': user_id, 'message': 'User profile'})


app = web.Application()
app.router.add_get('/', hello)
app.router.add_get('/users/{user_id}', user_handler)


if __name__ == '__main__':
    web.run_app(app, host='localhost', port=8080)
```

Run it with `python server.py`.

## Verify it worked

With the server running, open [http://localhost:8080/](http://localhost:8080/) or
[http://localhost:8080/users/123](http://localhost:8080/users/123) in your browser.

Then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and go to the **Live**
view. Within a few seconds you should see a span for the request. Click it to see its duration, the
method and path, and the response status.

<!-- TODO(app-verify): screenshot of an AIOHTTP server request span in the Live view, showing the method, path, and status -->

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_aiohttp_server()`.** Configure the
  connection first, then instrument.
- **You call `instrument_aiohttp_server()` exactly once**, before you start serving.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually sent a request.** Spans appear only after the server is hit; reload one of the URLs
  above.

## Advanced

### Passing options to the OpenTelemetry instrumentor

The keyword arguments of
[`logfire.instrument_aiohttp_server()`][logfire.Logfire.instrument_aiohttp_server] are passed to the
`AioHttpServerInstrumentor().instrument()` method of the
[OpenTelemetry AIOHTTP server instrumentation package][opentelemetry-aiohttp-server].

## Reference

- API reference:
  [`logfire.instrument_aiohttp_server()`][logfire.Logfire.instrument_aiohttp_server]
- Underlying OpenTelemetry package:
  [AIOHTTP server instrumentation][opentelemetry-aiohttp-server]

[aiohttp]: https://docs.aiohttp.org/en/stable/
[opentelemetry-aiohttp-server]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_server/aiohttp_server.html
