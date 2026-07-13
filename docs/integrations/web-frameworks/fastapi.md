---
title: "Instrument FastAPI: see every request your app handles"
description: "Add a few lines to your FastAPI app and see every request in Logfire: the endpoint, timing, the parsed and validated arguments, and any errors."
integration: otel
---
# FastAPI

See every request your [FastAPI][fastapi] app handles (the endpoint, how long it took, the parsed and
validated arguments, and any validation errors) as a **trace** (the full journey of one request,
made of nested **spans**, where each span is one unit of work with a name, a start, and a duration) in
Logfire.

## What you'll capture

- Each request as a span, with its HTTP status and duration
- The matched endpoint and any path or query parameters
- The parsed and validated arguments passed to your endpoint function
- Validation errors, with the fields that failed

!!! note "This captures request data"
    The endpoint arguments and path/query parameters recorded here can contain personal data (names, emails, tokens). They're sent to and stored in Logfire as span attributes. Use [scrubbing](../../how-to-guides/scrubbing.md) to redact sensitive values before they leave your machine, or `request_attributes_mapper` (see [Advanced](#endpoint-arguments-and-validation-errors)) to control exactly what's recorded.

{{ before_you_start() }}

## Installation

Install `logfire` with the `fastapi` extra:

{{ install_logfire(extras=['fastapi']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] to record every request.

To run the example below, also install [Uvicorn][uvicorn], the server that runs the app:

```bash
pip install uvicorn
```

```py title="main.py" hl_lines="7-8" skip-run="true" skip-reason="server-start"
from fastapi import FastAPI

import logfire

app = FastAPI()

logfire.configure()
logfire.instrument_fastapi(app)


@app.get('/hello')
async def hello(name: str):
    return {'message': f'hello {name}'}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app)
```

Run it with `python main.py`.

## Verify it worked

With the app running, open
[http://localhost:8000/hello?name=world](http://localhost:8000/hello?name=world) in your browser.

Then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and go to the **Live**
view. Within a few seconds you should see a span for the `GET /hello` request. Click it to see its
duration, the `name` argument (`world`), and the response status.

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_fastapi()`.** Configure the connection
  first, then instrument the app.
- **You call `instrument_fastapi(app)` exactly once**, on the same `app` object you serve.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually sent a request.** Spans appear only after the endpoint is hit; reload the URL above.

## Advanced

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] accepts arbitrary additional
keyword arguments and passes them to the OpenTelemetry `FastAPIInstrumentor.instrument_app()` method.
See [their documentation][opentelemetry-fastapi] for the full list.

### Endpoint arguments and validation errors

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] adds these attributes to each
request span:

- `fastapi.arguments.values`: a dictionary mapping the endpoint function's argument names to their
  parsed and validated values.
- `fastapi.arguments.errors`: a list of validation errors for any invalid inputs.

You can customize these attributes by passing a `request_attributes_mapper` function to
`instrument_fastapi`. It's called with the `Request` or `WebSocket` object and a dictionary containing
the keys `values` and `errors` above, and returns a new dictionary of attributes. For example, to
record only validation errors and drop valid arguments:

```py skip-run="true" skip-reason="server-start"
import logfire

app = ...


def request_attributes_mapper(request, attributes):
    if attributes['errors']:
        # Only log validation errors, not valid arguments
        return {
            # This will become the `fastapi.arguments.errors` attribute
            'errors': attributes['errors'],
            # Arbitrary custom attributes can also be added here
            'my_custom_attribute': ...,
        }
    else:
        # Don't log anything for valid requests
        return {}


logfire.configure()
logfire.instrument_fastapi(app, request_attributes_mapper=request_attributes_mapper)
```

!!! note
    The [`request_attributes_mapper`][logfire.Logfire.instrument_fastapi(request_attributes_mapper)]
    function must not mutate the contents of `values` or `errors`, but it can safely replace them
    with new values.

### Timing of argument parsing and endpoint execution

[`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi] also adds these timing attributes
to each request span:

- When parsing arguments and resolving dependencies started and ended:
    - `fastapi.arguments.start_timestamp`
    - `fastapi.arguments.end_timestamp`
- When the endpoint function itself started and ended executing, excluding time spent on dependencies
  and middleware:
    - `fastapi.endpoint_function.start_timestamp`
    - `fastapi.endpoint_function.end_timestamp`

### Extra spans for argument parsing and endpoint execution

You can add child spans for argument parsing and endpoint execution with
`logfire.instrument_fastapi(app, extra_spans=True)`. The main request span still carries the
attributes above; it just gains two extra child spans. This is mostly redundant now and is provided
mainly for backwards compatibility. It can help group together child logs and spans produced during
the request.

### Proxying browser telemetry

If your frontend sends telemetry from the browser, **never expose your Logfire write token in
frontend code**: anyone who loads the page could read it and send data to your project.

Instead, use an experimental proxy handler to forward OpenTelemetry Protocol (OTLP) data (the
standard wire format Logfire uses to receive telemetry) through your FastAPI backend, where the token
stays secret. See the
[Logfire JS browser package docs](https://pydantic.dev/docs/logfire/typescript-sdk/packages/browser/#python-backend-proxy)
for setup.

## Reference

- API reference: [`logfire.instrument_fastapi()`][logfire.Logfire.instrument_fastapi]
- Underlying OpenTelemetry package: [FastAPI instrumentation][opentelemetry-fastapi]

[fastapi]: https://fastapi.tiangolo.com/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[opentelemetry-fastapi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
[uvicorn]: https://www.uvicorn.org/
