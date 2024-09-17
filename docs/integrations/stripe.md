# Stripe

[Stripe] is a popular payment gateway that allows businesses to accept payments online.

The stripe Python client has both synchronous and asynchronous methods for making requests to the Stripe API.

By default, the stripe client uses the `requests` package for making synchronous requests and
the `httpx` package for making asynchronous requests.

```py
from stripe import StripeClient

client = StripeClient(api_key='<your_secret_key>')

# Synchronous request
client.customers.list()  # uses `requests`

# Asynchronous request
async def main():
    await client.customers.list_async()  # uses `httpx`

if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

You read more about this on the [Configuring an HTTP Client] section on the stripe repository.

## Synchronous Requests

As mentioned, by default, `stripe` uses the `requests` package for making HTTP requests.

In this case, you'll need to call [`logfire.instrument_requests()`][logfire.Logfire.instrument_requests].

```py
import os
from logging import basicConfig

import logfire
from stripe import StripeClient

logfire.configure()
logfire.instrument_requests()

client = StripeClient(api_key=os.getenv('STRIPE_SECRET_KEY'))

with logfire.span('list customers'):
    client.customers.list()
```

!!! note
    If you use the `http_client` parameter to configure the stripe client to use a different HTTP client,
    you'll need to call the appropriate instrumentation method.

## Asynchronous Requests

As mentioned, by default, `stripe` uses the `httpx` package for making asynchronous HTTP requests.

In this case, you'll need to call [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx].

```py
import asyncio
import os
from logging import basicConfig

import logfire
from stripe import StripeClient

logfire.configure()
logfire.instrument_httpx()     # for asynchronous requests

client = StripeClient(api_key=os.getenv('STRIPE_SECRET_KEY'))

async def main():
    with logfire.span('list async'):
        await client.customers.list_async()

if __name__ == '__main__':
    asyncio.run(main())
```

!!! note
    If you use the `http_client` parameter to configure the stripe client to use a different HTTP client,
    you'll need to call the appropriate instrumentation method.

## Add logging instrumentation

Stripe also has a logger (`logger = getLogger('stripe')`) that you can instrument with **Logfire**.

```py hl_lines="8"
import os
from logging import basicConfig

import logfire
from stripe import StripeClient

logfire.configure()
basicConfig(handlers=[logfire.LogfireLoggingHandler()], level='INFO')

client = StripeClient(api_key=os.getenv('STRIPE_SECRET_KEY'))


with logfire.span('list customers'):
    client.customers.list()
```

You can change the `level=INFO` to `level=DEBUG` to see even more details, like the response body.

[Stripe]: https://stripe.com
[Configure an HTTP Client]: https://github.com/stripe/stripe-python#configuring-an-http-client
