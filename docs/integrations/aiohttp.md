# AIOHTTP Client

[AIOHTTP][aiohttp] is an asynchronous HTTP client/server framework for asyncio and Python.

The [`logfire.instrument_aiohttp_client()`][logfire.Logfire.instrument_aiohttp_client] method will create a span for every request made by your AIOHTTP clients.

!!! question "What about AIOHTTP Server?"
    The AIOHTTP server instrumentation is not supported yet. You can track the progress [here][aiohttp-server].

## Installation

Install `logfire` with the `aiohttp` extra:

{{ install_logfire(extras=['aiohttp']) }}

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

## Masking URL in AIOHTTP span
To mask a URL for sensitive data you create add a AIOHTTP opentelemetry request hook.

```python
import aiohttp
from opentelemetry.trace import Span
from yarl import URL


def mask_url(url: URL) -> str:
    ...


def otel_request_hook(span: Span, params: aiohttp.TraceRequestStartParams):
    if span and span.is_recording():
        masked_url = mask_url(params.url)
        span.set_attribute("http.url", masked_url)

```

Now configure logfire to use this request hook
```python
logfire.instrument_aiohttp_client(request_hook=otel_request_hook)
```

[aiohttp]: https://docs.aiohttp.org/en/stable/
[aiohttp-server]: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/501
[opentelemetry-aiohttp]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_client.html
