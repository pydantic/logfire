# [Starlette][starlette]

The [OpenTelemetry Instrumentation Starlette][opentelemetry-starlette] package can be used to instrument Starlette.

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
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route

logfire.configure()


async def home(request: Request) -> PlainTextResponse:
    return PlainTextResponse("Hello, world!")


app = Starlette(routes=[Route("/", home)])
StarletteInstrumentor.instrument_app(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
```

!!! question "What about the OpenTelemetry ASGI middleware?"
    If you are a more experienced user, you might be wondering why we are not using
    the [OpenTelemetry ASGI middleware][opentelemetry-asgi]. The reason is that the
    `StarletteInstrumentor` actually wraps the ASGI middleware and adds some additional
    information related to the routes.

[starlette]: https://www.starlette.io/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-starlette]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html
[uvicorn]: https://www.uvicorn.org/
