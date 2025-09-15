---
integration: otel
---

# AIOHTTP Client

[AIOHTTP][aiohttp] is an asynchronous HTTP client/server framework for asyncio and Python.

The [`logfire.instrument_aiohttp_client()`][logfire.Logfire.instrument_aiohttp_client] method will create a span for every request made by your AIOHTTP clients.

For AIOHTTP server instrumentation, see [here](../web-frameworks/aiohttp.md).

## Installation

Install `logfire` with the `aiohttp-client` extra:

{{ install_logfire(extras=['aiohttp-client']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

```py title="main.py"
import logfire
import aiohttp


logfire.configure()
logfire.instrument_aiohttp_client()


async def main():
    async with aiohttp.ClientSession() as session:
        await session.get("https://httpbin.org/get")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

The keyword arguments of `logfire.instrument_aiohttp_client()` are passed to the `AioHttpClientInstrumentor().instrument()` method of the OpenTelemetry aiohttp client Instrumentation package, read more about it [here][opentelemetry-aiohttp].

## Configuration

The `logfire.instrument_aiohttp_client()` method accepts various parameters to configure the instrumentation.

### Capture Everything

You can capture all information (headers and response bodies) by setting the `capture_all` parameter to `True`.

```py
import aiohttp
import logfire

logfire.configure()
logfire.instrument_aiohttp_client(capture_all=True)

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.post("https://httpbin.org/post", json={"key": "value"}) as response:
            await response.json()
```

### Capture HTTP Headers

By default, **Logfire** doesn't capture HTTP headers. You can enable it by setting the `capture_headers` parameter to `True`.

```py
import aiohttp
import logfire

logfire.configure()
logfire.instrument_aiohttp_client(capture_headers=True)

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://httpbin.org/get") as response:
            await response.text()
```

This will capture both request and response headers.

### Capture HTTP Response Bodies

By default, **Logfire** doesn't capture HTTP response bodies. You can enable it by setting the `capture_response_body` parameter to `True`.

```py
import aiohttp
import logfire

logfire.configure()
logfire.instrument_aiohttp_client(capture_response_body=True)

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://httpbin.org/get") as response:
            await response.json()  # Body will be captured when read
```

### Request Body Capture (Not Supported)

!!! warning "Request Body Capture Not Implemented"
    Request body capture (`capture_request_body` parameter) is currently **not implemented** for aiohttp client instrumentation.
    
#### Capture Only Request Headers

Instead of capturing both request and response headers, you can create a request hook to capture only the request headers:

```py
import aiohttp
import logfire
from aiohttp.tracing import TraceRequestStartParams
from opentelemetry.trace import Span


def capture_request_headers(span: Span, params: TraceRequestStartParams):
    headers = params.headers
    span.set_attributes(
        {
            f'http.request.header.{header_name}': headers.getall(header_name)
            for header_name in headers.keys()
        }
    )


logfire.configure()
logfire.instrument_aiohttp_client(request_hook=capture_request_headers)

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://httpbin.org/get") as response:
            await response.text()
```

#### Capture Only Response Headers

Similarly, you can create a response hook to capture only the response headers:

```py
import aiohttp
import logfire
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams
from opentelemetry.trace import Span


def capture_response_headers(span: Span, params: TraceRequestEndParams | TraceRequestExceptionParams):
    if hasattr(params, 'response') and params.response:
        headers = params.response.headers
        span.set_attributes(
            {f'http.response.header.{header_name}': headers.getall(header_name)
            for header_name in headers.keys()}
        )


logfire.configure()
logfire.instrument_aiohttp_client(response_hook=capture_response_headers)

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://httpbin.org/get") as response:
            await response.text()
```

You can also use the hooks to filter headers or modify them before capturing them.

## Hiding sensitive URL parameters

The `url_filter` keyword argument can be used to modify the URL that's recorded in spans. Here's an example of how to use this to redact query parameters:

```python
from yarl import URL

def mask_url(url: URL) -> str:
    sensitive_keys = {"username", "password", "token", "api_key", "api_secret", "apikey"}
    masked_query = {key: "*****" if key in sensitive_keys else value for key, value in url.query.items()}
    return str(url.with_query(masked_query))

logfire.instrument_aiohttp_client(url_filter=mask_url)
```

[aiohttp]: https://docs.aiohttp.org/en/stable/
[opentelemetry-aiohttp]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_client.html
