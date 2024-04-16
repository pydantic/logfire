# ASGI

If the [ASGI][asgi] framework doesn't have a dedicated OpenTelemetry package, you can use the
[OpenTelemetry ASGI middleware][opentelemetry-asgi].

## Installation

You need to install the `opentelemetry-instrumentation-asgi` package:

```bash
pip install opentelemetry-instrumentation-asgi
```

## Usage

Below we have a minimal example using [Uvicorn][uvicorn]. You can run it with `python main.py`:

```py title="main.py"
import logfire
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware


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

app = OpenTelemetryMiddleware(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
```

You can read more about the OpenTelemetry ASGI middleware [here][opentelemetry-asgi].

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use_cases/web_frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html#capture-http-request-and-response-headers)

[asgi]: https://asgi.readthedocs.io/en/latest/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
[uvicorn]: https://www.uvicorn.org/
