# Cloudflare Workers And Deno

Use this for edge runtimes that are not ordinary Node.js servers.

## Cloudflare Workers

Install:

```bash
npm install @pydantic/logfire-cf-workers logfire
```

Enable Node.js compatibility:

```json
{
  "compatibility_flags": ["nodejs_compat"]
}
```

For `wrangler.toml`:

```toml
compatibility_flags = ["nodejs_compat"]
```

Set local development values in `.dev.vars`. Workers don't auto-read `.logfire/logfire_credentials.json` the way Python's SDK does, but the token in it is still the one to reuse here rather than minting a new one — see [auth.md](../auth.md)'s "If the calling skill needs a write token" section:

```bash
LOGFIRE_TOKEN=your-write-token
LOGFIRE_ENVIRONMENT=development
```

Store production tokens as Worker secrets, minted separately from **Project Settings → Write tokens** (a long-lived deployed Worker shouldn't share a credential with your local CLI session):

```bash
npx wrangler secret put LOGFIRE_TOKEN
```

Wrap the exported handler. Import manual spans and logs from `logfire`.

```ts
import * as logfire from 'logfire'
import { instrument } from '@pydantic/logfire-cf-workers'

const handler = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    logfire.info('worker request handled')
    return new Response('hello from Logfire')
  },
} satisfies ExportedHandler<Env>

export default instrument(handler, {
  service: {
    name: 'checkout-worker',
    namespace: '',
    version: '1.0.0',
  },
})
```

If wrapping a business function, avoid the name collision by aliasing:

```ts
import { instrument as instrumentFunction } from 'logfire'
import { instrument as instrumentWorker } from '@pydantic/logfire-cf-workers'
```

Cloudflare export is tied to request lifetime through `ctx.waitUntil()`. Use `ctx.waitUntil()` for asynchronous work that should be included in request-lifetime telemetry.

## Cloudflare Tail Workers

For Tail Worker flows, use `instrumentTail()` in the producer Worker and `exportTailEventsToLogfire()` in the Tail Worker. Follow the SDK examples when wiring producer and tail projects; do not improvise the event shape.

## Deno

Deno has built-in OpenTelemetry support. Configure OTLP export to Logfire and use the core package for manual spans. Deno is a generic-OpenTelemetry setup like any non-native-SDK language — for the write token in the header below, reuse what `projects use` already created rather than minting a new one; see [auth.md](../auth.md)'s "If the calling skill needs a write token" section:

```bash
OTEL_DENO=true \
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://logfire-api.pydantic.dev/v1/traces \
OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token' \
deno run --unstable-otel --allow-net main.ts
```

Manual API:

```ts
import * as logfire from 'npm:logfire'

await logfire.span('deno task', {
  attributes: { runtime: 'deno' },
  callback: async () => {
    logfire.info('running deno task')
  },
})
```

Preserve existing Deno permissions and add only the permissions required by the app and Deno OpenTelemetry configuration.
