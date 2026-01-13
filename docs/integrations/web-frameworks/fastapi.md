---
title: "Logfire Web Framework Integrations: FastAPI"
description: Connect Logfire to your FastAPI app. Follow our simple install flow using Uvicorn.
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

```py title="main.py" hl_lines="6-7"
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

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] adds the following attributes to the request spans:

- `fastapi.arguments.values`: A dictionary mapping argument names of the endpoint function to parsed and validated values.
- `fastapi.arguments.errors`: A list of validation errors for any invalid inputs.

You can customize these attributes by passing a `request_attributes_mapper` function to `instrument_fastapi`.
This function will be called with the `Request` or `WebSocket` object
and a dictionary containing keys `values` and `errors` corresponding to the attributes above.
It should return a new dictionary of attributes. For example:

```py
import logfire

app = ...


def request_attributes_mapper(request, attributes):
    if attributes["errors"]:
        # Only log validation errors, not valid arguments
        return {
            # This will become the `fastapi.arguments.errors` attribute
            "errors": attributes["errors"],
            # Arbitrary custom attributes can also be added here
            "my_custom_attribute": ...,
        }
    else:
        # Don't log anything for valid requests
        return {}


logfire.configure()
logfire.instrument_fastapi(app, request_attributes_mapper=request_attributes_mapper)
```

!!! note
    The [`request_attributes_mapper`][logfire.Logfire.instrument_fastapi(request_attributes_mapper)] function mustn't mutate the
    contents of `values` or `errors`, but it can safely replace them with new values.

## Timestamps of argument parsing and endpoint execution

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] also adds the following attributes to the request spans:

- The times when parsing arguments and resolving dependencies started and ended:
    - `fastapi.arguments.start_timestamp`
    - `fastapi.arguments.end_timestamp`
- The times when the actual endpoint function started and ended executing, leaving out the time spent on dependencies and middleware:
    - `fastapi.endpoint_function.start_timestamp`
    - `fastapi.endpoint_function.end_timestamp`

## Spans for argument parsing and endpoint execution

You can also enable spans for argument parsing and endpoint execution with `logfire.instrument_fastapi(app, extra_spans=True)`.
The main request span will still have the attributes described above, but it will also have two extra child spans.
This is mostly redundant now and is mainly provided for backwards compatibility.
It can also be useful for grouping together child logs and spans produced by the request.

[fastapi]: https://fastapi.tiangolo.com/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-fastapi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
[uvicorn]: https://www.uvicorn.org/
