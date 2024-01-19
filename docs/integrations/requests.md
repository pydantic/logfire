# [Requests][requests]

The [OpenTelemetry Instrumentation Requests][opentelemetry-requests] package can be used to instrument Requests.

## Installation

Install `logfire` with the `requests` extra:

{{ install_logfire(extras=['requests']) }}

## Usage

```py
import logfire
import requests
from opentelemetry.instrumentation.requests import RequestsInstrumentor

logfire.configure()
RequestsInstrumentor().instrument()

requests.get("https://httpbin.org/get")
```

You can read more about the [`requests`][requests] OpenTelemetry package [here][opentelemetry-requests].

[opentelemetry-requests]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
[requests]: https://docs.python-requests.org/en/master/
