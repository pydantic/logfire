---
title: Pydantic Logfire Browser Integration
description: "Guide for tracing browser activity: Learn how to set up getwebautoinstrumentations and configure a proxy to send frontend traces securely to Logfire."
integration: logfire
---
# Browser

The `@pydantic/logfire-browser` NPM package wraps [OpenTelemetry browser tracing](https://opentelemetry.io/docs/languages/js/getting-started/browser/) with sensible defaults and provides a simple API for creating spans and reporting exceptions.

!!! info "Securely Sending Traces"
    Logfire does not directly expose an endpoint suitable for sending traces from the browser, as this would make your write token publicly accessible.

    To safely send traces, you must route them through a backend proxy that attaches the `Authorization` header server-side.
    - **Python:** Use the built-in `logfire_proxy` handler for [FastAPI](../web-frameworks/fastapi.md#proxying-browser-telemetry) or [Starlette](../web-frameworks/starlette.md#proxying-browser-telemetry).
    - **Next.js:** Check out the [Next.js proxy example implementation](https://github.com/pydantic/logfire-js/blob/main/examples/nextjs-client-side-instrumentation/proxy.ts).

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
