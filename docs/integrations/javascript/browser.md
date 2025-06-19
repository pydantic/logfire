---
integration: logfire
---

# Browser

The `@pydantic/logfire-browser` NPM package wraps [OpenTelemetry browser tracing](https://opentelemetry.io/docs/languages/js/getting-started/browser/) with sensible defaults and provides a simple API for creating spans and reporting exceptions.

!!! info
    Logfire does not directly expose an endpoint suitable for sending traces from the browser, as this would make your write token publicly accessible. To send traces from the browser, you must create a proxy in your app that **forwards requests from your browser instrumentation to Logfire** while adding the `Authorization` header. Check the [Next.js middleware example implementation](https://github.com/pydantic/logfire-js/blob/main/examples/nextjs-client-side-instrumentation/middleware.ts#L8) for more details.


## Simple Usage

```ts
import { getWebAutoInstrumentations } from "@opentelemetry/auto-instrumentations-web";
import * as logfire from '@pydantic/logfire-browser';

// Set the path to your traces proxy endpoint - assuming it's hosted at `/client-traces`, same domain.
const url = new URL(window.location.href);
url.pathname = "/client-traces";

logfire.configure({
  traceUrl: url.toString(),
  serviceName: 'my-service',
  serviceVersion: '0.1.0',
  // The instrumentations to use
  // https://www.npmjs.com/package/@opentelemetry/auto-instrumentations-web - for more options and configuration
  instrumentations: [
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
