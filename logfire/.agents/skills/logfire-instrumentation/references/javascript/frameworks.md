# JavaScript Framework Setup

## Node.js (Express, Fastify, etc.)

Create `instrumentation.ts` and load it before your app:

```typescript
// instrumentation.ts
import * as logfire from '@pydantic/logfire-node'
import 'dotenv/config'

logfire.configure()
```

Launch:

```bash
node --require ./instrumentation.js app.js
# or with ts-node:
npx ts-node --require ./instrumentation.ts app.ts
```

The SDK auto-instruments common libraries (http, fetch, express, etc.) when loaded before the app via `--require`.

## Cloudflare Workers

```typescript
import { instrument } from '@pydantic/logfire-cf-workers'

const handler = {
    async fetch(request: Request, env: Env, ctx: ExecutionContext) {
        return new Response('Hello')
    },
}

export default instrument(handler, {
    service: { name: 'my-worker', version: '1.0.0' },
})
```

Add `LOGFIRE_TOKEN` to `.dev.vars` and enable `nodejs_compat` in `wrangler.toml`:

```toml
compatibility_flags = ["nodejs_compat"]
```

## Next.js / Vercel

Set environment variables in `.env.local` or Vercel dashboard:

```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://logfire-api.pydantic.dev/v1/traces
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://logfire-api.pydantic.dev/v1/metrics
OTEL_EXPORTER_OTLP_HEADERS=Authorization=<your-write-token>
```

Optionally use the `logfire` package for manual spans in server components and API routes:

```typescript
import * as logfire from 'logfire'

logfire.info('Server action executed', { action: 'createUser' })
```

## Deno

Deno has built-in OpenTelemetry support. Set environment variables:

```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://logfire-api.pydantic.dev/v1/traces
OTEL_EXPORTER_OTLP_HEADERS=Authorization=<your-write-token>
```

Run with telemetry enabled:

```bash
deno run --allow-env --unstable-otel app.ts
```
