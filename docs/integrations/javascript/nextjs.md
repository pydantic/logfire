---
integration: logfire
---

# Next.js

## Server-side Instrumentation

Vercel provides a comprehensive OpenTelemetry integration through the
`@vercel/otel` package. After following
[Vercel's integration instructions](https://vercel.com/docs/otel), add the
following environment variables to your project:

```sh
OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
```

This configuration directs the OpenTelemetry instrumentation to send data to Logfire.

!!! note
    Vercel production deployments use a caching mechanism that may prevent
    configuration changes from taking effect immediately or prevent spans from being reported. If you
    don't see spans appearing in Logfire, you can
    [clear the data cache for your project](https://vercel.com/docs/data-cache/manage-data-cache).

Optionally, you can use the Logfire API package to create manual spans.
Install the `@pydantic/logfire-api` NPM package and call the appropriate methods
from your server-side code:

```tsx
import * as logfire from "@pydantic/logfire-api";

export default async function Home() {
  return logfire.span("A warning span", {}, {
    level: logfire.Level.Warning,
  }, async (span) => {
    logfire.info("Nested info span");
      // Call span.end() to ensure the span is properly reported
    span.end();
    return <div>Hello</div>;
  });
}
```

A working example can be found in the [examples/nextjs](https://github.com/pydantic/logfire-js/tree/main/examples/nextjs) directory.

## Client-side Instrumentation

Client-side instrumentation can be implemented using the `@pydantic/logfire-browser` package. To set it up, you need to complete the following steps:

- Add a [proxy to the Logfire traces endpoint in `middleware.ts`](https://github.com/pydantic/logfire-js/blob/main/examples/nextjs-client-side-instrumentation/middleware.ts) to prevent exposing your Logfire write token.
- Wrap the browser instrumentation in [a client-only React component](https://github.com/pydantic/logfire-js/blob/main/examples/nextjs-client-side-instrumentation/app/components/ClientInstrumentationProvider.tsx). Use `next/dynamic` to ensure the component renders only in the browser ([see example](https://github.com/pydantic/logfire-js/blob/main/examples/nextjs-client-side-instrumentation/app/page.tsx#L5-L8)).

A complete working example can be found in the [examples/nextjs-client-side-instrumentation](https://github.com/pydantic/logfire-js/tree/main/examples/nextjs-client-side-instrumentation) directory.
