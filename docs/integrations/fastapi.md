# FastAPI

**Logfire** provides custom instrumentation for [FastAPI][fastapi]. It also works with the
third-party [OpenTelemetry FastAPI Instrumentation][opentelemetry-fastapi] package. The two can be used together or
separately.

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

Then visit http://localhost:8000/hello?name=world and check the logs.

## OpenTelemetry FastAPI Instrumentation

The third-party [OpenTelemetry FastAPI Instrumentation][opentelemetry-fastapi] package adds spans to every request with
detailed attributes about the HTTP request such as the full URL and the user agent. The start and end times let you see
how long it takes to process each request.

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] applies this instrumentation by default.
You can disable it by passing `use_opentelemetry_instrumentation=False`.

To customize this aspect of the instrumentation, use the package directly, e.g:

```py
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import logfire

# Or just remove this line completely if you don't want logfire's instrumentation at all
logfire.instrument_fastapi(app, use_opentelemetry_instrumentation=False)

# Whether or not you call the above, this is still needed to connect logfire with other instrumentation.
logfire.configure()

FastAPIInstrumentor.instrument_app(app, **custom_kwargs)
```

!!! question "What about the OpenTelemetry ASGI middleware?"
    If you are a more experienced user, you might be wondering about the [OpenTelemetry ASGI middleware][opentelemetry-asgi].
    The `FastAPIInstrumentor` actually wraps the ASGI middleware and adds some additional information related to the routes.

    Using the ASGI middleware directly as above will also work.

## Logfire instrumentation: logging endpoint arguments and validation errors

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] will emit a log message for each request.
By default this will contain the following attributes:

- `values`: A dictionary mapping argument names of the endpoint function to parsed and validated values.
- `errors`: A list of validation errors for any invalid inputs.

You can customize this by passing an `request_attributes_mapper` function to `instrument_fastapi`. This function will be called
with the `Request` or `WebSocket` object and the default attributes dictionary. It should return a new dictionary of
attributes, or `None` to skip logging this request. For example:

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


logfire.instrument_fastapi(app, request_attributes_mapper=request_attributes_mapper)
```

!!! note
    The [`request_attributes_mapper`][logfire.Logfire.instrument_fastapi(request_attributes_mapper)] function mustn't modify the
    contents of `values` or `errors`.

## Excluding URLs from instrumentation

To avoid tracing certain URLs, you can specify a string of comma-separated regexes which will be matched against the full request URL. This can be passed to:

- [`instrument_fastapi`][logfire.Logfire.instrument_fastapi] as [`excluded_urls`][logfire.Logfire.instrument_fastapi(excluded_urls)], e.g: `logfire.instrument_fastapi(app, excluded_urls='/health')`
- [`FastAPIInstrumentor.instrument_app`][opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app] as `excluded_urls` (only needed if you're already using the OpenTelemetry FastAPI Instrumentation directly)
- The environment variable `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`.
- The environment variable `OTEL_PYTHON_EXCLUDED_URLS` (which will also apply to other instrumentation).

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use_cases/web_frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html#capture-http-request-and-response-headers)

[fastapi]: https://fastapi.tiangolo.com/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-fastapi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
[uvicorn]: https://www.uvicorn.org/
