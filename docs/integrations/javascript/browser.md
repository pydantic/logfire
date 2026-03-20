---
title: Pydantic Logfire Browser Integration
description: "Guide for tracing browser activity: Learn how to set up getwebautoinstrumentations and configure a proxy to send frontend traces securely to Logfire."
integration: logfire
---
# Browser

The `@pydantic/logfire-browser` NPM package wraps [OpenTelemetry browser tracing](https://opentelemetry.io/docs/languages/js/getting-started/browser/) with sensible defaults and provides a simple API for creating spans and reporting exceptions.

!!! info "Securely Sending Traces"
    Logfire does not directly expose an endpoint suitable for sending traces from the browser, as this would make your write token publicly accessible.

    To safely send traces, you must create a proxy in your app that **forwards requests from your browser instrumentation to Logfire** while attaching the `Authorization` header server-side.
    - **Python:** See [Proxying Browser Telemetry](#proxying-browser-telemetry) below for FastAPI, Starlette, and generic framework examples.
    - **Next.js:** Check out the[Next.js proxy example implementation](https://github.com/pydantic/logfire-js/blob/main/examples/nextjs-client-side-instrumentation/proxy.ts)

## Simple Usage

```ts
import { getWebAutoInstrumentations } from "@opentelemetry/auto-instrumentations-web";
import * as logfire from '@pydantic/logfire-browser';

// Set the path to your backend proxy endpoint
// For example, if using the Python `logfire_proxy` handler hosted on the same domain:
const url = new URL(window.location.href);
url.pathname = "/logfire-proxy/v1/traces";

logfire.configure({
  traceUrl: url.toString(),
  serviceName: 'my-service',
  serviceVersion: '0.1.0',
  // The instrumentations to use
  // https://www.npmjs.com/package/@opentelemetry/auto-instrumentations-web - for more options and configuration
  instrumentations:[
    getWebAutoInstrumentations()
  ],
  // This outputs details about the generated spans in the browser console, use only in development and for troubleshooting.
  diagLogLevel: logfire.DiagLogLevel.ALL
})

```

!!! info
    the `@pydantic/logfire-browser` package is bundled as an ESM module, that's supported by all modern frameworks and browsers.

Note that if you're using an SSR/SSG framework, you should ensure that the code above runs only in the browser runtime.
[A dedicated example for Next.js](https://github.com/pydantic/logfire-js/tree/main/examples/nextjs-client-side-instrumentation) is available.


## Proxying Browser Telemetry

If you use a Python backend, logfire provide experimental tools in the `logfire.experimental.forwarding` module to easily create this proxy.

### FastAPI

For FastAPI, logfire provide a built-in `logfire_proxy` handler that safely buffers requests to prevent memory exhaustion DoS attacks.

```py title="main.py" skip-run="true" skip-reason="server-start"
from fastapi import FastAPI, Request

import logfire
from logfire.experimental.forwarding import logfire_proxy

logfire.configure()
app = FastAPI()


# Mount the proxy handler
# Note: {path:path} is strictly required to capture the OTLP route (e.g., /v1/traces)
@app.post('/logfire-proxy/{path:path}')
async def proxy_browser_telemetry(request: Request):
    return await logfire_proxy(request)
```

By default, this endpoint is unauthenticated and accepts payloads up to 50MB. In production, you should protect it using FastAPI dependencies to prevent abuse:

```py skip-run="true" skip-reason="server-start"
from fastapi import Depends, FastAPI, Request

import logfire
from logfire.experimental.forwarding import logfire_proxy

logfire.configure()
app = FastAPI()


async def verify_user_session():
    # Implement your authentication/rate-limiting logic here
    pass


@app.post('/logfire-proxy/{path:path}', dependencies=[Depends(verify_user_session)])
async def proxy_browser_telemetry_secure(request: Request):
    return await logfire_proxy(request)
```

### Starlette

For Starlette, you can mount the `logfire_proxy` handler directly as a route.

```py title="main.py" skip-run="true" skip-reason="server-start"
from starlette.applications import Starlette
from starlette.routing import Route

import logfire
from logfire.experimental.forwarding import logfire_proxy

logfire.configure()

app = Starlette(
    routes=[
        # Note: {path:path} is strictly required to capture the OTLP route (e.g., /v1/traces)
        Route('/logfire-proxy/{path:path}', logfire_proxy, methods=['POST'])
    ]
)
```

!!! warning "Security Note"
    By default, this endpoint is unauthenticated. In production, ensure you wrap your route with appropriate authentication middleware or rate-limiting to prevent unauthorized clients from sending arbitrary telemetry to your Logfire project.

### Generic Python Frameworks

If you are using another web framework (such as Django, Flask, Litestar, or a custom HTTP server), you can use the underlying `forward_export_request` function directly.

You simply extract the path, headers, and body from your framework's request object, pass them to `forward_export_request` as keyword arguments, and return the resulting status code, headers, and content.

```py title="main.py" skip-run="true" skip-reason="server-start"
import logfire
from logfire.experimental.forwarding import forward_export_request

logfire.configure()

# Example generic route handler:
def my_custom_proxy_route(request):

    # 1. Extract data from your framework's request object
    path = request.path      # e.g. "/v1/traces"
    headers = request.headers
    body = request.read()

    # 2. Forward the request to Logfire
    response = forward_export_request(
        path=path,
        headers=headers,
        body=body
    )

    # 3. Return the Logfire response to the browser
    return CustomFrameworkResponse(
        content=response.content,
        status_code=response.status_code,
        headers=response.headers
    )
```
