---
title: "Instrument HTTPX: see every outgoing request your app makes"
description: "Add a few lines to your HTTPX code and see every outgoing HTTP request in Logfire: the URL, status, how long it took, and any errors."
integration: otel
---
# HTTPX

See every HTTP request your app makes with [HTTPX][httpx]: the URL, the response status, how long it
took, and any errors, as a **span** (one unit of work with a name, a start, and a duration) in
Logfire. Related spans link together into a **trace** (the full journey of one request), so a slow
outgoing call shows up right next to the code that triggered it.

This works with both the synchronous `httpx.Client` and the asynchronous `httpx.AsyncClient`.

## What you'll capture

- Each request as a span, with its URL, method, response status, and duration
- Any errors that occurred during the request
- Optionally, request and response headers and bodies (off by default: see below)

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `httpx` extra:

{{ install_logfire(extras=['httpx']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] to record every request.

=== "Instrument every client"

    ```py title="main.py" hl_lines="8" skip-run="true" skip-reason="external-connection"
    import asyncio

    import httpx

    import logfire

    logfire.configure()
    logfire.instrument_httpx()

    url = 'https://httpbin.org/get'

    with httpx.Client() as client:
        client.get(url)


    async def main():
        async with httpx.AsyncClient() as client:
            await client.get(url)


    asyncio.run(main())
    ```

=== "Instrument a single client"

    ```py title="main.py" hl_lines="12 18" skip-run="true" skip-reason="external-connection"
    import asyncio

    import httpx

    import logfire

    logfire.configure()

    url = 'https://httpbin.org/get'

    with httpx.Client() as client:
        logfire.instrument_httpx(client)
        client.get(url)


    async def main():
        async with httpx.AsyncClient() as client:
            logfire.instrument_httpx(client)
            await client.get(url)


    asyncio.run(main())
    ```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for the `GET` request. Click it to see the URL, response status, and how long it
took.

<!-- TODO(app-verify): screenshot of the outgoing GET request span in the Live view, showing the URL, status, and duration -->

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_httpx()`.** Configure the connection first,
  then instrument.
- **You instrument the client you actually call.** `instrument_httpx()` with no argument covers all
  clients; if you pass a specific client, make sure it's the one making the request.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually made a request.** Spans appear only after a request completes.

## Advanced

The [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] method accepts several parameters
to control what's captured.

### Capture everything

Capture all request and response headers and bodies by setting `capture_all=True`. This sends that
data to Logfire, so avoid it if your requests carry secrets or personally identifiable information
(PII).

```py skip-run="true" skip-reason="external-connection"
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_all=True)

client = httpx.Client()
client.post('https://httpbin.org/post', json={'key': 'value'})
```

### Capture HTTP headers

By default, Logfire doesn't record HTTP headers. Turn them on with `capture_headers=True`:

```py skip-run="true" skip-reason="external-connection"
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_headers=True)

client = httpx.Client()
client.get('https://httpbin.org/get')
```

#### Capture only request headers

Instead of capturing both request and response headers, you can use a request hook to capture only the
request headers:

```py skip-run="true" skip-reason="external-connection"
import httpx
from opentelemetry.trace import Span

import logfire
from logfire.integrations.httpx import RequestInfo


def capture_request_headers(span: Span, request: RequestInfo):
    headers = request.headers
    span.set_attributes(
        {f'http.request.header.{header_name}': headers.get_list(header_name) for header_name in headers.keys()}
    )


logfire.configure()
logfire.instrument_httpx(request_hook=capture_request_headers)

client = httpx.Client()
client.get('https://httpbin.org/get')
```

#### Capture only response headers

Similarly, use a response hook to capture only the response headers:

```py skip-run="true" skip-reason="external-connection"
import httpx
from opentelemetry.trace import Span

import logfire
from logfire.integrations.httpx import RequestInfo, ResponseInfo


def capture_response_headers(span: Span, request: RequestInfo, response: ResponseInfo):
    headers = response.headers
    span.set_attributes(
        {f'http.response.header.{header_name}': headers.get_list(header_name) for header_name in headers.keys()}
    )


logfire.configure()
logfire.instrument_httpx(response_hook=capture_response_headers)

client = httpx.Client()
client.get('https://httpbin.org/get')
```

You can also use these hooks to filter or modify headers before capturing them.

### Capture HTTP bodies

By default, Logfire doesn't record HTTP bodies. Turn them on with `capture_request_body` and
`capture_response_body`. As with headers, this sends the body data to Logfire, so avoid it for
requests that carry sensitive data.

```py skip-run="true" skip-reason="external-connection"
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(
    capture_request_body=True,
    capture_response_body=True,
)

client = httpx.Client()
client.post('https://httpbin.org/post', data='Hello, World!')
```

## Reference

- API reference: [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx]
- Underlying OpenTelemetry package: [HTTPX instrumentation][opentelemetry-httpx]

[httpx]: https://www.python-httpx.org/
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
