# AIOHTTP Client

[AIOHTTP][aiohttp] is an asynchronous HTTP client/server framework for asyncio and Python.

The [OpenTelemetry Instrumentation AIOHTTP][opentelemetry-aiohttp] package can be used to instrument AIOHTTP.

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
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor


logfire.configure()
AioHttpClientInstrumentor().instrument()

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://httpbin.org/get") as response:
            await response.text()

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

You can read more about the AIOHTTP OpenTelemetry package [here][opentelemetry-aiohttp].

[aiohttp]: https://docs.aiohttp.org/en/stable/
[aiohttp-server]: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/501
[opentelemetry-aiohttp]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_client.html
