# [WSGI][wsgi]

The analogous applies to WSGI. If the WSGI framework doesn't have a dedicated OpenTelemetry
package, you can use the [OpenTelemetry WSGI middleware][opentelemetry-wsgi].

## Installation

You need to install the [`opentelemetry-instrumentation-wsgi`][pypi-otel-wsgi] package:

```bash
pip install opentelemetry-instrumentation-wsgi
```

## Usage

Below we have a minimal example using the standard library [`wsgiref`][wsgiref]. You can run it with `python main.py`:

```py title="main.py"
from wsgiref.simple_server import make_server

from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware


def app(env, start_response):
    start_response('200 OK', [('Content-Type','text/html')])
    return [b"Hello World"]

app = OpenTelemetryMiddleware(app)

with make_server("", 8000, app) as httpd:
    print("Serving on port 8000...")

    # Serve until process is killed
    httpd.serve_forever()
```

You can read more about the OpenTelemetry WSGI middleware [here][opentelemetry-wsgi].

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](../http_servers.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html#capture-http-request-and-response-headers)

[wsgi]: https://wsgi.readthedocs.io/en/latest/
[opentelemetry-wsgi]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html
[pypi-otel-wsgi]: https://pypi.org/project/opentelemetry-instrumentation-wsgi/
[wsgiref]: https://docs.python.org/3/library/wsgiref.html
