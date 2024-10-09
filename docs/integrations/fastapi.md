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

Then visit http://localhost:8000/hello?name=world and check the logs.

## OpenTelemetry FastAPI Instrumentation

The third-party [OpenTelemetry FastAPI Instrumentation][opentelemetry-fastapi] package adds spans to every request with
detailed attributes about the HTTP request such as the full URL and the user agent. The start and end times let you see
how long it takes to process each request.

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] applies this instrumentation by default.
You can disable it by passing `use_opentelemetry_instrumentation=False`.

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] also accepts arbitrary additional keyword arguments
and passes them to the OpenTelemetry `FastAPIInstrumentor.instrument_app()` method. See their documentation for more details.

## Logfire instrumentation: logging endpoint arguments and validation errors

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

## Excluding URLs from instrumentation

To avoid tracing certain URLs, you can specify a string of comma-separated regexes which will be matched against the full request URL. This can be passed to:

- [`instrument_fastapi`][logfire.Logfire.instrument_fastapi] as [`excluded_urls`][logfire.Logfire.instrument_fastapi(excluded_urls)], e.g: `logfire.instrument_fastapi(app, excluded_urls='/health')`
- The environment variable `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`.
- The environment variable `OTEL_PYTHON_EXCLUDED_URLS` (which will also apply to other instrumentation).

!!! example
    If you'd like to trace all URLs except the base `/` URL, you can use the following regex: `^https?://[^/]+/$`

    Breaking it down:
    * `^` matches the start of the string
    * `https?` matches `http` or `https`
    * `://` matches `://`
    * `[^/]+` matches one or more characters that are not `/`
    * `/` matches `/`
    * `$` matches the end of the string

    This instrumentation might look like:

    ```py
    from fastapi import FastAPI

    import logfire

    app = FastAPI()

    logfire.configure()
    logfire.instrument_fastapi(app, excluded_urls='^https?://[^/]+/$')

    if __name__ == '__main__':
        import uvicorn

        uvicorn.run(app)
    ```

    If you visit http://127.0.0.1:8000/, that matches the above regex, so no span will be sent to logfire.
    If you visit http://127.0.0.1:8000/hello/ (or any other endpoing that's not `/`, for that matter), a span will be sent to logfire.


## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use-cases/web-frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html#capture-http-request-and-response-headers)

[fastapi]: https://fastapi.tiangolo.com/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-fastapi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
[uvicorn]: https://www.uvicorn.org/
