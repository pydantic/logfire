# [FastAPI][fastapi]

The [OpenTelemetry Instrumentation FastAPI][opentelemetry-fastapi] package can be used to instrument FastAPI.

## Installation

Install `logfire` with the `fastapi` extra:

{{ install_logfire(extras=['fastapi']) }}

## Usage

We have a minimal example below. Please install [Uvicorn][uvicorn] to run it:

```bash
pip install uvicorn
```

You can run it with `python main.py`:

```py title="main.py"
import logfire
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

logfire.configure()

app = FastAPI()


@app.get("/foobar")
async def foobar():
    return {"message": "hello world"}


FastAPIInstrumentor.instrument_app(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
```

!!! question "What about the OpenTelemetry ASGI middleware?"
    If you are a more experienced user, you might be wondering why we are not using
    the [OpenTelemetry ASGI middleware][opentelemetry-asgi]. The reason is that the
    `FastAPIInstrumentor` actually wraps the ASGI middleware and adds some additional
    information related to the routes.

[fastapi]: https://fastapi.tiangolo.com/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-fastapi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
[uvicorn]: https://www.uvicorn.org/
