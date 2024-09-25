# Starlette

The [`logfire.instrument_starlette()`][logfire.Logfire.instrument_starlette] method will create a span for every request to your [Starlette][starlette] application.

## Installation

Install `logfire` with the `starlette` extra:

{{ install_logfire(extras=['starlette']) }}

## Usage

We have a minimal example below. Please install [Uvicorn][uvicorn] to run it:

```bash
pip install uvicorn
```

You can run it with `python main.py`:

```py title="main.py"
import logfire
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route

logfire.configure()


async def home(request: Request) -> PlainTextResponse:
    return PlainTextResponse("Hello, world!")


app = Starlette(routes=[Route("/", home)])
logfire.instrument_starlette(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
```

The keyword arguments of `logfire.instrument_starlette()` are passed to the `StarletteInstrumentor.instrument_app()` method of the OpenTelemetry Starlette Instrumentation package, read more about it [here][opentelemetry-starlette].

!!! question "What about the OpenTelemetry ASGI middleware?"
    If you are a more experienced user, you might be wondering why we are not using
    the [OpenTelemetry ASGI middleware][opentelemetry-asgi]. The reason is that the
    `StarletteInstrumentor` actually wraps the ASGI middleware and adds some additional
    information related to the routes.

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use-cases/web-frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html#capture-http-request-and-response-headers)

[starlette]: https://www.starlette.io/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-starlette]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html
[uvicorn]: https://www.uvicorn.org/
