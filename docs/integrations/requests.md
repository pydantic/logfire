# Requests

The logfire.instrument_requests() function can be used to instrument [Requests][requests] with Logfire.

## Installation

Install `logfire` with the `requests` extra:

{{ install_logfire(extras=['requests']) }}

## Usage

```py title="main.py"
import logfire
import requests

logfire.configure()
logfire.instrument_requests()

requests.get("https://httpbin.org/get")
```

You can read more about the [`requests`][requests] OpenTelemetry package [here][opentelemetry-requests].

[opentelemetry-requests]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
[requests]: https://docs.python-requests.org/en/master/
