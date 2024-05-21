# Requests

The [`logfire.instrument_requests()`][logfire.Logfire.instrument_requests] method can be used to
instrument [`requests`][requests] with **Logfire**.

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

[`logfire.instrument_requests()`][logfire.Logfire.instrument_requests] uses the
**OpenTelemetry requests Instrumentation** package,
which you can find more information about [here][opentelemetry-requests].

[opentelemetry-requests]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
[requests]: https://docs.python-requests.org/en/master/
