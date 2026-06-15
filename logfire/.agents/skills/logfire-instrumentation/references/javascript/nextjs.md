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

Add browser tracing only when the app has or can safely add a same-origin proxy. Install:

```bash
npm install @pydantic/logfire-browser @opentelemetry/auto-instrumentations-web
```

Create a proxy file in the project root or `src` directory. For Next.js 16 and later use `proxy.ts`. For older apps that already use `middleware.ts`, follow the existing file convention unless the app has migrated to `proxy.ts`.

```ts
// proxy.ts
import { NextRequest, NextResponse } from 'next/server'

export default function proxy(request: NextRequest) {
  const url = request.nextUrl.clone()

  if (url.pathname === '/logfire-proxy/v1/traces') {
    const token = process.env.LOGFIRE_TOKEN
    if (!token) {
      return new NextResponse('Logfire token is not configured', { status: 500 })
    }

    const requestHeaders = new Headers(request.headers)
    requestHeaders.set('Authorization', token)

    return NextResponse.rewrite(new URL('https://logfire-api.pydantic.dev/v1/traces'), {
      request: {
        headers: requestHeaders,
      },
    })
  }

  return NextResponse.next()
}

export const config = {
  matcher: '/logfire-proxy/:path*',
}
```

Set `LOGFIRE_TOKEN` server-side to a Logfire write token. It can be the same write token value used in `OTEL_EXPORTER_OTLP_HEADERS`, but it must not use a `NEXT_PUBLIC_` prefix.

Create a client-only component:

```tsx
'use client'

import { getWebAutoInstrumentations } from '@opentelemetry/auto-instrumentations-web'
import * as logfire from '@pydantic/logfire-browser'
import { useEffect } from 'react'

export function ClientInstrumentation() {
  useEffect(() => {
    const shutdown = logfire.configure({
      traceUrl: '/logfire-proxy/v1/traces',
      serviceName: 'nextjs-browser',
      instrumentations: [getWebAutoInstrumentations()],
    })

    return () => {
      void shutdown()
    }
  }, [])

  return null
}
```

If importing the component from server-rendered code, use `next/dynamic` with `ssr: false`.

## Vercel Deployment Notes

- Add OTLP and Logfire token values to the Vercel project environment.
- If spans do not appear after changing tracing env vars, clear the Vercel data cache for the project and redeploy.
- Keep server and browser service names distinct when both are enabled.
