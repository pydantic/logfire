# [WSGI][wsgi]

The analogous applies to WSGI. If the WSGI framework doesn't have a dedicated OpenTelemetry
package, you can use the [OpenTelemetry WSGI middleware][opentelemetry-wsgi].

```py
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

app = ...

app = OpenTelemetryMiddleware(app)
```

You can read more about the OpenTelemetry WSGI middleware [here][opentelemetry-wsgi].

[wsgi]: https://wsgi.readthedocs.io/en/latest/
[opentelemetry-wsgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html
