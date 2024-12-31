---
integration: otel
---

# ASGI

If the [ASGI][asgi] web framework you're using doesn't have a dedicated integration, you can use the
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

[asgi]: https://asgi.readthedocs.io/en/latest/
[uvicorn]: https://www.uvicorn.org/
