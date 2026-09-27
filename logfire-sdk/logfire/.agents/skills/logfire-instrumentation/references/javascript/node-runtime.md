# Node.js Runtime Instrumentation

Use this for Express, Fastify, Koa, Hono on Node, background workers, CLIs, and scripts. For Next.js without a custom server, use [nextjs.md](./nextjs.md) instead.

## Install

Install in the app package:

```bash
npm install @pydantic/logfire-node @opentelemetry/auto-instrumentations-node
```

Use the repo's package manager. If peer dependency warnings name additional `@opentelemetry/*` packages, install the reported peers.

## Instrumentation File

Create an instrumentation module that is loaded before the app imports instrumented libraries:

```ts
// instrumentation.ts
import 'dotenv/config'
import * as logfire from '@pydantic/logfire-node'

logfire.configure({
  serviceName: process.env.LOGFIRE_SERVICE_NAME ?? 'node-service',
  serviceVersion: process.env.npm_package_version,
  environment: process.env.NODE_ENV,
})
```

For local debugging, add `console: true` or set `LOGFIRE_CONSOLE=true`.

## Startup Scripts

Preserve the existing runner and add a preload.

ESM or modern Node:

```json
{
  "scripts": {
    "start": "node --import ./dist/instrumentation.js ./dist/server.js"
  }
}
```

TypeScript during development with `tsx`:

```json
{
  "scripts": {
    "dev": "node --import tsx --import ./src/instrumentation.ts ./src/server.ts"
  }
}
```

CommonJS:

```js
// instrumentation.cjs
require('dotenv/config')
const logfire = require('@pydantic/logfire-node')

logfire.configure({ serviceName: process.env.LOGFIRE_SERVICE_NAME || 'node-service' })
```

```json
{
  "scripts": {
    "start": "node --require ./instrumentation.cjs ./server.cjs"
  }
}
```

Use `--require` only for CommonJS. Prefer `--import` for ESM and modern Node apps.

## Manual Spans In App Code

After the preload configures the SDK, app modules can import the same package for manual spans:

```ts
import * as logfire from '@pydantic/logfire-node'

app.get('/orders/:id', async (req, res) => {
  const order = await logfire.span('load order {order_id}', {
    attributes: { order_id: req.params.id },
    callback: async () => loadOrder(req.params.id),
  })

  res.json(order)
})
```

Express error handler:

```ts
app.use((err: Error, req: express.Request, res: express.Response, _next: express.NextFunction) => {
  logfire.reportError('express request failed', err, { path: req.path }, { tags: ['express'] })
  res.status(500).send('internal server error')
})
```

## Auto-Instrumentation Configuration

Disable noisy or unsafe instrumentations in `configure()`:

```ts
logfire.configure({
  serviceName: 'checkout-api',
  nodeAutoInstrumentations: {
    '@opentelemetry/instrumentation-fs': { enabled: false },
    '@opentelemetry/instrumentation-http': { enabled: true },
  },
})
```

Do not import Express, HTTP clients, database clients, or other instrumented libraries before this file is loaded.

## Scripts And CLIs

Short-lived processes should explicitly shut down:

```ts
try {
  await runJob()
  logfire.info('job finished')
} finally {
  await logfire.shutdown({ timeoutMillis: 5000 })
}
```

Use `forceFlush()` when the process continues but queued telemetry needs to be exported immediately.
