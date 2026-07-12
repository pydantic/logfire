---
title: "Instrument Requests: see every outgoing request your app makes"
description: "Add a few lines to your Requests code and see every outgoing HTTP request in Logfire: the URL, status, how long it took, and any errors."
integration: otel
---
# Requests

See every HTTP request your app makes with [`requests`][requests]: the URL, the response status, how
long it took, and any errors, as a **span** (one unit of work with a name, a start, and a duration)
in Logfire. Related spans link together into a **trace** (the full journey of one request), so a slow
outgoing call shows up right next to the code that triggered it.

## What you'll capture

- Each request as a span, with its URL, method, response status, and duration
- Any errors that occurred during the request

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `requests` extra:

{{ install_logfire(extras=['requests']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_requests()`][logfire.Logfire.instrument_requests] to record every request.

```py title="main.py" hl_lines="5-6" skip-run="true" skip-reason="external-connection"
import requests

import logfire

logfire.configure()
logfire.instrument_requests()

requests.get('https://httpbin.org/get')
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for the `GET` request. Click it to see the URL, response status, and how long it
took.

<!-- TODO(app-verify): screenshot of the outgoing GET request span in the Live view, showing the URL, status, and duration -->

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_requests()`.** Configure the connection
  first, then instrument.
- **You call `instrument_requests()` exactly once.**
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually made a request.** Spans appear only after a request completes.

## Advanced

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_requests()`][logfire.Logfire.instrument_requests] accepts additional keyword
arguments and passes them to the OpenTelemetry Requests instrumentation. See
[their documentation][opentelemetry-requests] for the full list.

## Reference

- API reference: [`logfire.instrument_requests()`][logfire.Logfire.instrument_requests]
- Underlying OpenTelemetry package: [Requests instrumentation][opentelemetry-requests]

[opentelemetry-requests]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html
[requests]: https://docs.python-requests.org/en/master/
