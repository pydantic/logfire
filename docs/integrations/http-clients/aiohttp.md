---
title: "Instrument AIOHTTP client: see every outgoing request your app makes"
description: "Add a few lines to your AIOHTTP client code and see every outgoing HTTP request in Logfire: the URL, status, how long it took, and any errors."
integration: otel
---
# AIOHTTP client

See every HTTP request your app makes with an [AIOHTTP][aiohttp] client: the URL, the response status,
how long it took, and any errors, as a **span** (one unit of work with a name, a start, and a
duration) in Logfire. Related spans link together into a **trace** (the full journey of one request),
so a slow outgoing call shows up right next to the code that triggered it.

This page covers AIOHTTP as an HTTP *client*. To instrument an AIOHTTP *server*, see
[AIOHTTP server](../web-frameworks/aiohttp.md).

## What you'll capture

- Each request as a span, with its URL, method, response status, and duration
- Any errors that occurred during the request
- Optionally, request and response headers and bodies (off by default: see below)

{{ before_you_start() }}

## Installation

Install `logfire` with the `aiohttp-client` extra:

{{ install_logfire(extras=['aiohttp-client']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_aiohttp_client()`][logfire.Logfire.instrument_aiohttp_client] to record every
request.

```py title="main.py" hl_lines="6" skip-run="true" skip-reason="external-connection"
import aiohttp

import logfire

logfire.configure()
logfire.instrument_aiohttp_client()


async def main():
    async with aiohttp.ClientSession() as session:
        await session.get('https://httpbin.org/get')


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for the `GET` request. Click it to see the URL, response status, and how long it
took.

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_aiohttp_client()`.** Configure the
  connection first, then instrument.
- **You call `instrument_aiohttp_client()` exactly once.**
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually made a request.** Spans appear only after a request completes.

## Advanced

The [`logfire.instrument_aiohttp_client()`][logfire.Logfire.instrument_aiohttp_client] method accepts
several parameters to control what's captured.

### Capture everything

Capture all request and response headers and bodies by setting `capture_all=True`. This sends that
data to Logfire, so avoid it if your requests carry secrets or personally identifiable information
(PII).

```py skip-run="true" skip-reason="external-connection"
import aiohttp

import logfire

logfire.configure()
logfire.instrument_aiohttp_client(capture_all=True)


async def main():
    async with aiohttp.ClientSession() as session:
        await session.post('https://httpbin.org/post', json={'key': 'value'})


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

### Capture HTTP headers

By default, Logfire doesn't record HTTP headers. Turn them on with `capture_headers=True`:

```py skip-run="true" skip-reason="external-connection"
import aiohttp

import logfire

logfire.configure()
logfire.instrument_aiohttp_client(capture_headers=True)


async def main():
    async with aiohttp.ClientSession() as session:
        await session.get('https://httpbin.org/get')


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

#### Capture only request headers

Instead of capturing both request and response headers, you can use a request hook to capture only the
request headers:

```py skip-run="true" skip-reason="external-connection"
import aiohttp
from aiohttp.tracing import TraceRequestStartParams
from opentelemetry.trace import Span

import logfire


def capture_request_headers(span: Span, request: TraceRequestStartParams):
    headers = request.headers
    span.set_attributes(
        {f'http.request.header.{header_name}': headers.getall(header_name) for header_name in headers.keys()}
    )


logfire.configure()
logfire.instrument_aiohttp_client(request_hook=capture_request_headers)


async def main():
    async with aiohttp.ClientSession() as session:
        await session.get('https://httpbin.org/get')


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

#### Capture only response headers

Similarly, use a response hook to capture only the response headers:

```py skip-run="true" skip-reason="external-connection"
import aiohttp
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams
from opentelemetry.trace import Span

import logfire


def capture_response_headers(span: Span, response: 'TraceRequestEndParams | TraceRequestExceptionParams'):
    if hasattr(response, 'response') and response.response:
        headers = response.response.headers
        span.set_attributes(
            {f'http.response.header.{header_name}': headers.getall(header_name) for header_name in headers.keys()}
        )


logfire.configure()
logfire.instrument_aiohttp_client(response_hook=capture_response_headers)


async def main():
    async with aiohttp.ClientSession() as session:
        await session.get('https://httpbin.org/get')


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

Inside a hook you choose which headers to record on the span. If you also set `capture_headers=True`, though, Logfire records the headers before your hook runs, so a hook can't redact those after the fact; use [scrubbing](../../how-to-guides/scrubbing.md) for that.

### Capture HTTP bodies

By default, Logfire doesn't record HTTP bodies. Turn them on with `capture_request_body` and
`capture_response_body`. As with headers, this sends the body data to Logfire, so avoid it for
requests that carry sensitive data.

```py skip-run="true" skip-reason="external-connection"
import aiohttp

import logfire

logfire.configure()
logfire.instrument_aiohttp_client(
    capture_request_body=True,
    capture_response_body=True,
)


async def main():
    async with aiohttp.ClientSession() as session:
        response = await session.post('https://httpbin.org/post', data='Hello, World!')
        await response.text()


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

### Hiding sensitive URL parameters

Use the `url_filter` keyword argument to change the URL recorded in spans, for example to redact
sensitive query parameters:

```python skip-run="true" skip-reason="external-connection"
from yarl import URL

import logfire


def mask_url(url: URL) -> str:
    sensitive_keys = {
        'username',
        'password',
        'token',
        'api_key',
        'api_secret',
        'apikey',
    }
    masked_query = {key: '*****' if key in sensitive_keys else value for key, value in url.query.items()}
    return str(url.with_query(masked_query))


logfire.instrument_aiohttp_client(url_filter=mask_url)
```

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_aiohttp_client()`][logfire.Logfire.instrument_aiohttp_client] accepts additional
keyword arguments and passes them to the OpenTelemetry AIOHTTP client instrumentation. See
[their documentation][opentelemetry-aiohttp] for the full list.

## Reference

- API reference: [`logfire.instrument_aiohttp_client()`][logfire.Logfire.instrument_aiohttp_client]
- Underlying OpenTelemetry package: [AIOHTTP client instrumentation][opentelemetry-aiohttp]

[aiohttp]: https://docs.aiohttp.org/en/stable/
[opentelemetry-aiohttp]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_client.html
