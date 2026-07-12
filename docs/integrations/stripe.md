---
title: "Instrument Stripe: trace calls to the Stripe API"
description: "See every request the Stripe Python client makes, sync or async, as spans in Logfire, with duration, status, and errors."
integration: otel
---
# Stripe

See every call your app makes to [Stripe](https://stripe.com) (the payment platform's API) as a
**span** (one timed step, with a name and a duration) in Logfire, with how long it took, its status,
and any errors.

The Stripe Python client sends these calls over HTTP, so you instrument it by instrumenting the HTTP
library it uses under the hood: there's no separate Stripe extra to install. By default the client
uses the [`requests`](http-clients/requests.md) package for synchronous calls and the
[`httpx`](http-clients/httpx.md) package for asynchronous calls, so which Logfire function you call
depends on which style you use.

## What you'll capture

- Each Stripe API call as a span, with its duration and status
- Any errors returned by Stripe
- Optionally, Stripe's own log messages (see [Advanced](#advanced))

## Before you start

You'll need two things:

- **A Logfire project and its write token** (the key your app uses to send data). Create one and copy
  it from **Project → Settings → Write tokens**. See [Getting Started](../index.md).
- **A Stripe secret key**, from your Stripe dashboard. The examples read it from the
  `STRIPE_SECRET_KEY` environment variable.

## Installation

Install `logfire`. No Stripe-specific extra is needed:

{{ install_logfire() }}

This works with your existing `stripe` package. If you don't have it yet, `pip install stripe`.

## Usage

Call `logfire.configure()` to connect to your project, then instrument the HTTP library the Stripe
client uses.

For **synchronous** calls (the default), the client uses `requests`, so call
[`logfire.instrument_requests()`][requests-section]:

```py skip-run="true" skip-reason="external-connection"
import os

from stripe import StripeClient

import logfire

logfire.configure()
logfire.instrument_requests()

client = StripeClient(api_key=os.getenv('STRIPE_SECRET_KEY'))

client.customers.list()
```

For **asynchronous** calls (methods ending in `_async`), the client uses `httpx`, so call
[`logfire.instrument_httpx()`][httpx-section]:

```py skip-run="true" skip-reason="external-connection"
import asyncio
import os

from stripe import StripeClient

import logfire

logfire.configure()
logfire.instrument_httpx()  # for asynchronous requests

client = StripeClient(api_key=os.getenv('STRIPE_SECRET_KEY'))


async def main():
    with logfire.span('list async'):
        await client.customers.list_async()


if __name__ == '__main__':
    asyncio.run(main())
```

!!! note
    If you set the Stripe client's `http_client` parameter to use a different HTTP library, call the
    matching Logfire instrumentation method for that library instead. See
    [Configuring an HTTP Client](https://github.com/stripe/stripe-python#configuring-an-http-client) in
    the Stripe repository for the details.

## Verify it worked

Run your program, then open the [Live view](../guides/web-ui/live.md). Within a few seconds you'll see
a span for the HTTP call to Stripe, with its duration and status.

<!-- TODO(app-verify): screenshot of a Stripe API call span in the Live view, showing the request URL and duration -->

## Troubleshooting

Not seeing your Stripe calls in Logfire? Check that `logfire.configure()` ran before the
`instrument_*` call, that your write token is set, that you instrumented the HTTP library your calls
actually use (`requests` for synchronous, `httpx` for asynchronous), and that your `STRIPE_SECRET_KEY`
is set so the call succeeds.

## Advanced

### Add Stripe's log messages

Stripe has its own logger (`getLogger('stripe')`) that
[you can route to Logfire](logging.md). This adds Stripe's internal log lines alongside the request
spans:

```py skip-run="true" skip-reason="external-connection" hl_lines="8-9"
import os
from logging import basicConfig

from stripe import StripeClient

import logfire

logfire.configure()
basicConfig(handlers=[logfire.LogfireLoggingHandler()], level='INFO')

client = StripeClient(api_key=os.getenv('STRIPE_SECRET_KEY'))

client.customers.list()
```

Change `level='INFO'` to `level='DEBUG'` to see more detail, including the response body. Note that
`DEBUG` level can include sensitive data, so use it with care.

## Reference

- [`logfire.instrument_requests()`][requests-section]: instrument synchronous Stripe calls.
- [`logfire.instrument_httpx()`][httpx-section]: instrument asynchronous Stripe calls.
- [Stripe: Configuring an HTTP Client](https://github.com/stripe/stripe-python#configuring-an-http-client): how the client chooses its HTTP library.

[requests-section]: http-clients/requests.md
[httpx-section]: http-clients/httpx.md
