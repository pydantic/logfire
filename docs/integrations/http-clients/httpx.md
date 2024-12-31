---
integration: otel
---

# HTTPX

The [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] method can be used to instrument [HTTPX][httpx] with **Logfire**.

## Installation

Install `logfire` with the `httpx` extra:

{{ install_logfire(extras=['httpx']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

=== "Instrument the package"

    ```py title="main.py"
    import asyncio

    import httpx
    import logfire

    logfire.configure()
    logfire.instrument_httpx()

    url = "https://httpbin.org/get"

    with httpx.Client() as client:
        client.get(url)


    async def main():
        async with httpx.AsyncClient() as client:
            await client.get(url)


    asyncio.run(main())
    ```

=== "Instrument a single client"

    ```py title="main.py"
    import asyncio

    import httpx
    import logfire

    logfire.configure()

    url = 'https://httpbin.org/get'

    with httpx.Client() as client:
        logfire.instrument_httpx(client)
        client.get(url)


    async def main():
        async with httpx.AsyncClient() as client:
            logfire.instrument_httpx(client)
            await client.get(url)


    asyncio.run(main())
    ```

[`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] uses the
**OpenTelemetry HTTPX Instrumentation** package,
which you can find more information about [here][opentelemetry-httpx].

## Fine Tuning

The `logfire.instrument_httpx()` method accepts different parameters to fine-tune the instrumentation.

### Capture HTTP Headers

By default, **Logfire** doesn't capture HTTP headers. You can enable it by setting the `capture_headers` parameter to `True`.

```py
import httpx
import logfire

logfire.configure()
logfire.instrument_httpx(capture_headers=True)

client = httpx.Client()
client.get("https://httpbin.org/get")
```

#### Capture Only Request Headers

Instead of capturing both request and response headers, you can create a request hook to capture only the request headers:

```py
import httpx
import logfire
from logfire.integrations.httpx import RequestInfo
from opentelemetry.trace import Span


def capture_request_headers(span: Span, request: RequestInfo):
    headers = request.headers
    span.set_attributes(
        {
            f'http.request.header.{header_name}': headers.get_list(header_name)
            for header_name in headers.keys()
        }
    )


logfire.configure()
logfire.instrument_httpx(request_hook=capture_request_headers)

client = httpx.Client()
client.get("https://httpbin.org/get")
```

#### Capture Only Response Headers

Similarly, you can create a response hook to capture only the response headers:

```py
import httpx
import logfire
from opentelemetry.trace import Span
from logfire.integrations.httpx import RequestInfo, ResponseInfo


def capture_response_headers(span: Span, request: RequestInfo, response: ResponseInfo):
    headers = response.headers
    span.set_attributes(
        {f'http.response.header.{header_name}': headers.get_list(header_name)
        for header_name in headers.keys()}
    )


logfire.configure()
logfire.instrument_httpx(response_hook=capture_response_headers)

client = httpx.Client()
client.get('https://httpbin.org/get')
```

You can also use the hooks to filter headers or modify them before capturing them.

### Capture HTTP Body

By default, **Logfire** doesn't capture HTTP bodies.

To capture the request and response bodies, you need to set different parameters to `True`.

### Capture Request Body

To capture the request body when the `Content-Type` header is set to `application/json`, you can set
the `capture_request_json_body` parameter to `True`.

```py
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_request_json_body=True)

client = httpx.Client()
client.post("https://httpbin.org/post", json={"key": "value"})
```

To capture the request body when the `Content-Type` header is set to `application/x-www-form-urlencoded`, you can set
the `capture_request_form_data` parameter to `True`.

```py
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_request_form_data=True)

client = httpx.Client()
client.post("https://httpbin.org/post", data={"key": "value"})
```

To capture the request body when the `Content-Type` header is set to `text/*`, you can set
the `capture_request_text_body` parameter to `True`.

```py
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_request_text_body=True)

client = httpx.Client()
client.post("https://httpbin.org/post", content="Hello, World!")
```

### Capture Response Body

To capture the response body when the `Content-Type` header is set to `application/json`, you can set
the `capture_response_json_body` parameter to `True`.

```py
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_response_json_body=True)

client = httpx.Client()
client.get("https://httpbin.org/json")
```

To capture the response body when the `Content-Type` header is set to `text/*`, you can set
the `capture_response_text_body` parameter to `True`.

```py
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_response_text_body=True)

client = httpx.Client()
client.get("https://httpbin.org/get")
```

### Capture All Headers and Bodies

To capture all HTTP headers and bodies, you can set the `capture_all` parameter to `True`.

```py
import httpx

import logfire

logfire.configure()
logfire.instrument_httpx(capture_all=True)

client = httpx.Client()
client.get("https://httpbin.org/get")
```

[httpx]: https://www.python-httpx.org/
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
