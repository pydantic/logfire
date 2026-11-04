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

Use the [frontend specialist](https://pydantic.dev/.well-known/agent-skills/logfire-frontend/SKILL.md)
for client initialization, route grouping, capture policy, and replay. Browser
setup needs its restricted frontend application token, not this server's write
token. Keep browser and server telemetry separate.

## Vercel Deployment Notes

- Add server OTLP and ordinary Logfire token values to the Vercel project environment. Supply the separate frontend application configuration through the app's existing public runtime-config mechanism.
- If spans do not appear after changing tracing env vars, clear the Vercel data cache for the project and redeploy.
- Confirm server and browser data appear as distinct services; the frontend application's identity owns the browser service name.
