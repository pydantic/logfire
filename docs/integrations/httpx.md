# HTTPX

The [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] method can be used to instrument [HTTPX][httpx] with **Logfire**.

## Installation

Install `logfire` with the `httpx` extra:

{{ install_logfire(extras=['httpx']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

=== "Instrument the package"

    ```py title="main.py"
    import asyncio

    import httpx
    import logfire

    logfire.configure()
    logfire.instrument_httpx()

    url = "https://httpbin.org/get"

    with httpx.Client() as client:
        client.get(url)


    async def main():
        async with httpx.AsyncClient() as client:
            await client.get(url)


    asyncio.run(main())
    ```

=== "Instrument a single client"

    ```py title="main.py"
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

## Hooks

The `logfire.instrument_httpx()` method also accepts the following hooks:

- `request_hook`: called before sending a request.
- `response_hook`: called after receiving a response.
- `async_request_hook`: called before sending an async request.
- `async_response_hook`: called after receiving an async response.

You can use these hooks to add custom attributes that are not automatically captured by **Logfire**.

### (Async) Request Hook

The `request_hook` and `async_request_hook` hooks are called before sending a request. They receive two arguments:

```py title="main.py" hl_lines="24-27"
import asyncio
from collections import defaultdict

import httpx
from opentelemetry.instrumentation.httpx import RequestInfo
from opentelemetry.trace import Span

import logfire


def set_request_headers(span: Span, request: RequestInfo):
    method, url, headers, stream, extensions = request
    attributes: defaultdict[str, str] = defaultdict(list)
    for key, value in headers.items():
        key = key.lower()
        attributes[f'http.request.header.{key}'].append(value)
    span.set_attributes(attributes)


def request_hook(span: Span, request: RequestInfo):
    """This is called when using a `httpx.Client`."""
    set_request_headers(span, request)


async def async_request_hook(span: Span, request: RequestInfo):
    """This is called when using a `httpx.AsyncClient`."""
    set_request_headers(span, request)


logfire.configure()
logfire.instrument_httpx(request_hook=request_hook, async_request_hook=async_request_hook)

url = 'https://httpbin.org/get'

with httpx.Client() as client:
    client.get(url)


async def main():
    async with httpx.AsyncClient() as client:
        await client.get(url)


asyncio.run(main())
```

`RequestInfo` is a [`NamedTuple`][typing.NamedTuple] with the following attributes: `method`, `url`, `headers`, `stream`, and `extensions`.

!!! warning "Don't consume the stream"
    The `stream` is available, but you shouldn't use it.

    Once a generator is consumed, it cannot be consumed again. This means that if you consume the stream
    in the `request_hook` or `async_request_hook`, the request will fail.


### (Async) Response Hook

The `response_hook` and `async_response_hook` hooks are called after receiving a response. They receive three arguments:

```py title="main.py" hl_lines="29-32"
import asyncio
from collections import defaultdict

import httpx
from opentelemetry.instrumentation.httpx import RequestInfo, ResponseInfo
from opentelemetry.trace import Span

import logfire


def set_response_headers(span: Span, response: ResponseInfo):
    """Set the response headers as attributes on the span."""
    status_code, headers, stream, extensions = response
    attributes: defaultdict[str, str] = defaultdict(list)
    for key, value in headers.items():
        key = key.lower()
        attributes[f'http.response.header.{key}'].append(value)
    span.set_attributes(attributes)


def response_hook(span: Span, request: RequestInfo, response: ResponseInfo):
    """This is called when using a `httpx.Client`."""
    set_response_headers(span, response)


async def async_response_hook(span: Span, request: RequestInfo, response: ResponseInfo):
    """This is called when using a `httpx.AsyncClient`."""
    set_response_headers(span, response)


logfire.configure()
logfire.instrument_httpx(
    response_hook=response_hook,
    async_response_hook=async_response_hook
)

url = 'https://httpbin.org/get'

with httpx.Client() as client:
    client.get(url)

async def main():
    async with httpx.AsyncClient() as client:
        await client.get(url)


asyncio.run(main())
```

`ResponseInfo` is a [`NamedTuple`][typing.NamedTuple] with the following attributes: `status_code`, `headers`, `stream`, and `extensions`.

!!! warning "Don't consume the stream"
    The `stream` is available, but you shouldn't use it.

    Once a generator is consumed, it cannot be consumed again. This means that if you consume the stream
    in the `response_hook` or `async_response_hook`, the request will fail.

## More information

[`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] uses the
**OpenTelemetry HTTPX Instrumentation** package,
which you can find more information about [here][opentelemetry-httpx].

[httpx]: https://www.python-httpx.org/
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
