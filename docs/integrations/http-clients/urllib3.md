---
title: "Instrument urllib3: see every outgoing request your app makes"
description: "Add a few lines to your urllib3 code and see every outgoing HTTP request in Logfire: the URL, status, how long it took, and any errors."
integration: otel
---
# urllib3

See every HTTP request your app makes with [`urllib3`][urllib3]: the URL, the response status, how
long it took, and any errors, as a **span** (one unit of work: a single operation, with a name, a
start, and a duration) in Logfire. Related spans link together into a **trace** (the full journey of
one request), so a slow outgoing call shows up next to the code that triggered it.

## What you'll capture

- Each request as a span, with its URL, method, response status, and duration
- Any errors that occurred during the request

{{ before_you_start() }}

## Installation

Install `logfire` with the `urllib3` extra:

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
- **You call `instrument_urllib3()` exactly once.**
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually made a request.** Spans appear only after a request completes.

## Advanced

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_urllib3()`][logfire.Logfire.instrument_urllib3] accepts `excluded_urls`,
`request_hook`, `response_hook`, and `url_filter`. Additional keyword arguments are passed to the
OpenTelemetry urllib3 instrumentation. See [their documentation][opentelemetry-urllib3] for details.

## Reference

- API reference: [`logfire.instrument_urllib3()`][logfire.Logfire.instrument_urllib3]
- Underlying OpenTelemetry package: [urllib3 instrumentation][opentelemetry-urllib3]

[opentelemetry-urllib3]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/urllib3/urllib3.html
[urllib3]: https://urllib3.readthedocs.io/
