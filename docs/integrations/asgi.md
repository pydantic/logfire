# ASGI

If the [ASGI][asgi] framework doesn't have a dedicated OpenTelemetry package, you can use the
[`logfire.instrument_asgi()`][logfire.Logfire.instrument_asgi] method to instrument it.

## Installation

Install `logfire` with the `asgi` extra:

{{ install_logfire(extras=['asgi']) }}

## Usage

Below we have a minimal example using [Uvicorn][uvicorn]. You can run it with `python main.py`:

```py title="main.py"
import logfire


logfire.configure()


async def app(scope, receive, send):
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain"), (b"content-length", b"13")],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})

app = logfire.instrument_asgi(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
```

The keyword arguments of [`logfire.instrument_asgi()`][logfire.Logfire.instrument_asgi] are passed to the
[`OpenTelemetryMiddleware`][opentelemetry.instrumentation.asgi.OpenTelemetryMiddleware] class
of the OpenTelemetry ASGI Instrumentation package.

## Excluding URLs from instrumentation
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use-cases/web-frameworks.md#excluding-urls-from-instrumentation)

!!! note
    `OpenTelemetryMiddleware` does accept an `excluded_urls` parameter, but does not support specifying said URLs via an environment variable,
    unlike other instrumentations.

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use-cases/web-frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html#capture-http-request-and-response-headers)

[asgi]: https://asgi.readthedocs.io/en/latest/
[uvicorn]: https://www.uvicorn.org/
