# HTTPX

The [OpenTelemetry Instrumentation HTTPX][opentelemetry-httpx] package can be used to instrument [HTTPX][httpx].

## Installation

Install `logfire` with the `httpx` extra:

{{ install_logfire(extras=['httpx']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

```py title="main.py"
import logfire
import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

logfire.configure()
url = "https://httpbin.org/get"
HTTPXClientInstrumentor().instrument()

with httpx.Client() as client:
    client.get(url)


async def main():
    async with httpx.AsyncClient() as client:
        await client.get(url)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

You can read more about the HTTPX OpenTelemetry package [here][opentelemetry-httpx].

[httpx]: https://www.python-httpx.org/
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
