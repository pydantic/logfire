# [ASGI][asgi]

If the ASGI framework doesn't have a dedicated OpenTelemetry package, you can use the
[OpenTelemetry ASGI middleware][opentelemetry-asgi].

```py
import uvicorn
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

app = ...

app = OpenTelemetryMiddleware(app)

if __name__ == "__main__":
    uvicorn.run(app)
```

You can read more about the OpenTelemetry ASGI middleware [here][opentelemetry-asgi].

[asgi]: https://asgi.readthedocs.io/en/latest/
[opentelemetry-asgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asgi/asgi.html
