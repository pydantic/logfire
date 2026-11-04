---
title: "Instrument urllib3: see outgoing HTTP requests"
description: "Add a few lines to your urllib3 code and see every outgoing HTTP request in Logfire: the URL, status, how long it took, and any errors."
integration: otel
---
# urllib3

See outgoing HTTP requests made with [`urllib3`][urllib3]: the URL, the response status, how
long it took, and any errors, as a **span** (one unit of work: a single operation, with a name, a
start, and a duration) in Logfire. Related spans link together into a **trace** (the full journey of
one request), so a slow outgoing call shows up next to the code that triggered it.

## What you'll capture

- Each request as a span, with its URL, method, response status, and duration
- Errors that occur before urllib3 returns a response
- Metrics for request duration and body sizes

Logfire redacts URL credentials and common signed URL parameters. Other query parameters can appear
in traces. Use `url_filter` to remove them if your application puts sensitive values there. Header
capture is off by default, and the integration records body sizes without recording body contents.
For streamed responses, the span ends when urllib3 returns the response object. Errors while
reading the body later are outside that span.

{{ before_you_start() }}

## Installation

Install Logfire with the `urllib3` extra. The integration supports urllib3 1.x and 2.x and
requires OpenTelemetry's urllib3 instrumentor version `0.61b0` or later.

{{ install_logfire(extras=['urllib3']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_urllib3()`][logfire.Logfire.instrument_urllib3] to record every request.

```py title="main.py" hl_lines="5-6" skip-run="true" skip-reason="external-connection"
import urllib3

import logfire

logfire.configure()
logfire.instrument_urllib3()

http = urllib3.PoolManager()
http.request('GET', 'https://httpbin.org/get')
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for the `GET` request. Click it to see the URL, response status, and how long it
took.

## Troubleshooting

Not seeing your urllib3 requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_urllib3()`.** Configure the connection
  first, then instrument.
- **Check whether urllib3 is already instrumented.** Installation applies across the process,
  including to pools created before installation. If OpenTelemetry already instrumented urllib3,
  later calls keep the first installation's settings.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually made a request.** Spans appear only after a request completes.
- **A request raises `ValueError` while processing `Content-Length`.** OpenTelemetry urllib3
  instrumentation versions `0.61b0` through `0.66b0` can raise this error when the server sends an
  invalid length. Correct the server response or use `excluded_urls` to skip instrumentation for
  that URL.

## Advanced

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_urllib3()`][logfire.Logfire.instrument_urllib3] accepts `excluded_urls`,
`request_hook`, `response_hook`, and `url_filter`. Use `captured_request_headers` and
`captured_response_headers` to opt in to recording selected headers. Set `sensitive_headers` to
redact values for matching header names. OpenTelemetry also accepts environment variables for these
settings. Additional keyword arguments go to OpenTelemetry. See [their documentation][opentelemetry-urllib3] for details.

## Reference

- API reference: [`logfire.instrument_urllib3()`][logfire.Logfire.instrument_urllib3]
- Underlying OpenTelemetry package: [urllib3 instrumentation][opentelemetry-urllib3]

[opentelemetry-urllib3]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/urllib3/urllib3.html
[urllib3]: https://urllib3.readthedocs.io/
