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
