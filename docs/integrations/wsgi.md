# WSGI

If the [WSGI][wsgi] framework doesn't have a dedicated OpenTelemetry package, you can use the
[`logfire.instrument_wsgi()`][logfire.Logfire.instrument_wsgi] method to instrument it.

## Installation

Install `logfire` with the `wsgi` extra:

{{ install_logfire(extras=['wsgi']) }}

## Usage

Below we have a minimal example using the standard library [`wsgiref`][wsgiref]. You can run it with `python main.py`:

```py title="main.py"
from wsgiref.simple_server import make_server

import logfire


def app(env, start_response):
    start_response('200 OK', [('Content-Type','text/html')])
    return [b"Hello World"]

app = logfire.instrument_wsgi(app)

with make_server("", 8000, app) as httpd:
    print("Serving on port 8000...")

    # Serve until process is killed
    httpd.serve_forever()
```

The keyword arguments of [`logfire.instrument_wsgi()`][logfire.Logfire.instrument_wsgi] are passed to the
[`OpenTelemetryMiddleware`][opentelemetry.instrumentation.wsgi.OpenTelemetryMiddleware] class of
the OpenTelemetry WSGI Instrumentation package.


## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use-cases/web-frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html#capture-http-request-and-response-headers)

[wsgi]: https://wsgi.readthedocs.io/en/latest/
[wsgiref]: https://docs.python.org/3/library/wsgiref.html
