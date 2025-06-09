---
integration: otel
---

# AIOHTTP

[AIOHTTP][aiohttp] is an asynchronous HTTP client/server framework for asyncio and Python.

The [`logfire.instrument_aiohttp_client()`][logfire.Logfire.instrument_aiohttp_client] method will create a span for every request made by your AIOHTTP clients.

The [`logfire.instrument_aiohttp_server()`][logfire.Logfire.instrument_aiohttp_server] method will create a span for every request made by your AIOHTTP server.

## Installation

Install `logfire` with the `aiohttp` extra:

{{ install_logfire(extras=['aiohttp']) }}

## Client Usage

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

## Server Usage

You can also instrument aiohttp servers to create spans for every incoming request. Here's a minimal server example:

```py title="server.py"
import logfire
from aiohttp import web


logfire.configure()
logfire.instrument_aiohttp_server()


async def hello(request):
    return web.Response(text="Hello, World!")


async def user_handler(request):
    user_id = request.match_info['user_id']
    return web.json_response({"user_id": user_id, "message": "User profile"})


app = web.Application()
app.router.add_get('/', hello)
app.router.add_get('/users/{user_id}', user_handler)


if __name__ == "__main__":
    web.run_app(app, host='localhost', port=8080)
```

You can run this server with `python server.py` and then make requests to `http://localhost:8080/` or `http://localhost:8080/users/123` to see the spans created for each request.

The keyword arguments of `logfire.instrument_aiohttp_server()` are passed to the `AioHttpServerInstrumentor().instrument()` method of the OpenTelemetry aiohttp server Instrumentation package.

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
[aiohttp-server]: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/501
[opentelemetry-aiohttp]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_client.html
