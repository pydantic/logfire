---
integration: otel
---

# FastAPI

**Logfire** combines custom and third-party instrumentation for [FastAPI][fastapi]
with the [`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] method.

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

app = FastAPI()

logfire.configure()
logfire.instrument_fastapi(app)


@app.get("/hello")
async def hello(name: str):
    return {"message": f"hello {name}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
```

Then visit [http://localhost:8000/hello?name=world](http://localhost:8000/hello?name=world) and check the logs.

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] accepts arbitrary additional keyword arguments
and passes them to the OpenTelemetry `FastAPIInstrumentor.instrument_app()` method. See [their documentation][opentelemetry-fastapi] for more details.

## Endpoint arguments and validation errors

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] will emit a span for each request
called `FastAPI arguments` which shows how long it takes FastAPI to parse and validate the endpoint function
arguments from the request and resolve any dependencies.
By default the span will also contain the following attributes:

- `values`: A dictionary mapping argument names of the endpoint function to parsed and validated values.
- `errors`: A list of validation errors for any invalid inputs.

You can customize this by passing an `request_attributes_mapper` function to `instrument_fastapi`. This function will be called
with the `Request` or `WebSocket` object and the default attributes dictionary. It should return a new dictionary of
attributes, or `None` to set the span level to 'debug' so that it's hidden by default. For example:

```py
import logfire

app = ...


def request_attributes_mapper(request, attributes):
    if attributes["errors"]:
        # Only log validation errors, not valid arguments
        return {
            "errors": attributes["errors"],
            "my_custom_attribute": ...,
        }
    else:
        # Don't log anything for valid requests
        return None


logfire.configure()
logfire.instrument_fastapi(app, request_attributes_mapper=request_attributes_mapper)
```

!!! note
    The [`request_attributes_mapper`][logfire.Logfire.instrument_fastapi(request_attributes_mapper)] function mustn't mutate the
    contents of `values` or `errors`, but it can safely replace them with new values.

!!! note
    The attributes on the `FastAPI arguments` span are also set on the root span created by OpenTelemetry for easier querying.
    The `values` and `error` attributes are under the names `fastapi.arguments.values` and `fastapi.arguments.errors` to avoid name collisions.

[fastapi]: https://fastapi.tiangolo.com/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-fastapi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
[uvicorn]: https://www.uvicorn.org/
