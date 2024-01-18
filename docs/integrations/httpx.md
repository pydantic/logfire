#  [HTTPX][httpx]

The [OpenTelemetry Instrumentation HTTPX][opentelemetry-httpx] package can be used to instrument HTTPX.

## Installation

Install `logfire` with the `httpx` extra:

{{ install_logfire(extras=['httpx']) }}

## Usage

```py
import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

HTTPXClientInstrumentor().instrument()

with httpx.Client() as client:
    client.get("https://httpbin.org/get")
```

You can read more about the HTTPX OpenTelemetry package [here][opentelemetry-httpx].

[httpx]: https://www.python-httpx.org/
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
