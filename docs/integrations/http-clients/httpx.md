---
title: "Instrument HTTPX and HTTPX2: see every outgoing request your app makes"
description: "Add a few lines to your HTTPX or HTTPX2 code and see every outgoing HTTP request in Logfire: the URL, status, how long it took, and any errors."
integration: otel
---
# HTTPX and HTTPX2

See every HTTP request your app makes with [HTTPX][httpx] or [HTTPX2][httpx2]: the URL, the response
status, how long it took, and any errors, as a **span** (one unit of work with a name, a start, and a
duration) in Logfire. Related spans link together into a **trace** (the full journey of one request),
so a slow outgoing call shows up right next to the code that triggered it.

This works with the synchronous `Client` and asynchronous `AsyncClient` from either library. If both
libraries are installed, one call to `logfire.instrument_httpx()` instruments both when
`opentelemetry-instrumentation-httpx` is version 0.65b0 or newer. With an earlier version, Logfire
instruments HTTPX and warns that it skipped HTTPX2.

## What you'll capture

- Each request as a span, with its URL, method, response status, and duration
- Any errors that occurred during the request
- Optionally, request and response headers and bodies (off by default: see below)

{{ before_you_start() }}

## Installation

Install `logfire` with the `httpx` extra:

{{ install_logfire(extras=['httpx']) }}

The extra installs the OpenTelemetry integration that collects request data. It does not install
`httpx` or `httpx2`; keep the client library you use as an application dependency.

HTTPX2 support requires `opentelemetry-instrumentation-httpx` 0.65b0 or newer. A fresh installation
normally selects a compatible version. If an existing environment keeps an older version, use the
upgrade command in [Troubleshooting](#troubleshooting).

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] to record every request. With no
client argument, Logfire instruments both libraries when they are installed. Pass a client instance
to instrument only that client.

=== "Instrument all installed clients"

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

=== "Instrument one HTTPX2 client"

    ```py title="main.py" hl_lines="12 18" skip-run="true" skip-reason="external-connection"
    import asyncio

    import httpx2

    import logfire

    logfire.configure()

    url = 'https://httpbin.org/get'

    with httpx2.Client() as client:
        logfire.instrument_httpx(client)
        client.get(url)


    async def main():
        async with httpx2.AsyncClient() as client:
            logfire.instrument_httpx(client)
            await client.get(url)


    asyncio.run(main())
    ```

Run it with `python main.py`.

You can also pass one `httpx.Client` or `httpx.AsyncClient`; the Logfire call stays the same.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for the `GET` request. Click it to see the URL, response status, and how long it
took.

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_httpx()`.** Configure the connection first,
  then instrument.
- **You instrument the client you actually call.** `instrument_httpx()` with no argument covers both
  installed libraries; if you pass a specific client, make sure it's the one making the request.
- **HTTPX2 reports that it needs newer OpenTelemetry instrumentation.** Upgrade Logfire and the HTTPX
  integration together so their OpenTelemetry dependencies remain compatible:

  ```bash
  pip install -U 'logfire[httpx]' 'opentelemetry-instrumentation-httpx>=0.65b0'
  ```
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually made a request.** Spans appear only after a request completes.

## Advanced

The [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] method accepts several parameters
to control what's captured. The same capture settings and hooks apply to HTTPX and HTTPX2. The
examples below use HTTPX.

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

Inside a hook you choose which headers to record on the span. If you also set `capture_headers=True`, though, Logfire records the headers before your hook runs, so a hook can't redact those after the fact; use [scrubbing](../../how-to-guides/scrubbing.md) for that.

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
[httpx2]: https://github.com/pydantic/httpx2
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
