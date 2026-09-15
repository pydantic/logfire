# Next.js Instrumentation

Use this for Next.js apps. Instrument server-side Next telemetry separately from optional browser tracing.

## Server-Side Tracing

Install in the Next.js app package:

```bash
npm install @vercel/otel logfire
```

Create `instrumentation.ts` in the project root, or `src/instrumentation.ts` if the app uses `src`:

```ts
import { registerOTel } from '@vercel/otel'

export function register() {
  registerOTel({
    serviceName: process.env.LOGFIRE_SERVICE_NAME ?? 'nextjs-app',
  })
}
```

Set server-only env vars in `.env.local`, deployment secrets, or the hosting dashboard:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
LOGFIRE_SERVICE_NAME=nextjs-app
```

Do not prefix write-token variables with `NEXT_PUBLIC_`.

## Manual Server Spans

Use the runtime-agnostic `logfire` package in server components, route handlers, server actions, and other server-only code:

```tsx
import * as logfire from 'logfire'

export default async function Page() {
  return logfire.span('render home page', {
    callback: async () => {
      logfire.info('loading homepage data')
      return <main>Hello</main>
    },
  })
}
```

Route handler error reporting:

```ts
import * as logfire from 'logfire'

export async function POST(request: Request) {
  try {
    return Response.json(await createOrder(await request.json()))
  } catch (error) {
    logfire.reportError('create order route failed', error)
    throw error
  }
}
```

## Client-Side Browser Tracing

Browser tracing uses a frontend application, which supplies a restricted public token and pins the browser service identity at ingest. This is separate from the ordinary write token used by Next.js server-side tracing.

Open **Project settings → Frontend applications**, create or select the browser application, and copy its generated configuration. If that page is unavailable, explain that browser setup cannot continue with an ordinary write token and direct the user to [Logfire support](https://pydantic.dev/docs/logfire/get-started/help/).

Install:

```bash
npm install @pydantic/logfire-browser
```

Create a client-only component using the exact regional trace URL and restricted token from the generated setup. The restricted token is designed to be public and may be embedded in the client bundle or supplied through the app's public build/runtime configuration. Replace both placeholders before deploying:

```tsx
'use client'

import * as logfire from '@pydantic/logfire-browser'
import { useEffect, useRef } from 'react'

export function ClientInstrumentation() {
  const configured = useRef(false)

  useEffect(() => {
    if (!configured.current) {
      logfire.configure({
        traceUrl: '<generated-regional-trace-url>',
        traceExporterHeaders: () => ({
          Authorization: 'Bearer <frontend-application-token>',
        }),
        autoInstrumentations: true,
        rum: { webVitals: true },
      })
      configured.current = true
    }
  }, [])

  return null
}
```

Mount this component once at the app root and do not return the asynchronous SDK cleanup from its effect. The ref prevents React Strict Mode's development-only second effect setup from configuring Logfire twice. Tests, previews, or app shells that intentionally replace the whole telemetry setup should await the cleanup returned by `configure()` before configuring a replacement.

Import this Client Component normally from an App Router Server Component. If the app needs `next/dynamic` with `ssr: false`, put that dynamic import in another Client Component; Next.js rejects `ssr: false` directly in a Server Component.

Do not set `serviceName`, `serviceNamespace`, or the environment in browser configuration; the frontend application pins those values. Never substitute the server's `LOGFIRE_TOKEN` or another ordinary write token for the frontend application token.

If the repository already routes browser telemetry through a backend, preserve that architecture and follow the browser SDK guide's optional-proxy contract. Do not add a new Next.js rewrite merely to hide the restricted frontend token.

## Vercel Deployment Notes

- Add server OTLP and ordinary Logfire token values to the Vercel project environment. Supply the separate frontend application configuration through the app's existing public runtime-config mechanism.
- If spans do not appear after changing tracing env vars, clear the Vercel data cache for the project and redeploy.
- Confirm server and browser data appear as distinct services; the frontend application's identity owns the browser service name.
