---
integration: otel
---

# AIOHTTP Server

[AIOHTTP][aiohttp] is an asynchronous HTTP client/server framework for asyncio and Python.

The [`logfire.instrument_aiohttp_server()`][logfire.Logfire.instrument_aiohttp_server] method will create a span for every request made to your AIOHTTP server.

For AIOHTTP client instrumentation, see [here](../http-clients/aiohttp.md).

## Installation

Install `logfire` with the `aiohttp-server` extra:

{{ install_logfire(extras=['aiohttp-server']) }}

## Usage

Here's a minimal server example:

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

[aiohttp]: https://docs.aiohttp.org/en/stable/
[opentelemetry-aiohttp-server]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_client/aiohttp_server.html