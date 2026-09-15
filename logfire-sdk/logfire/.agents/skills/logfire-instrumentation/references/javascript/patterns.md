# JavaScript / TypeScript Manual API Patterns

Use this reference when adding manual spans, logs, function wrappers, error reporting, tags, baggage projection, sampling, or scrubbing to JS/TS code.

## Imports

Use the runtime package when it configures the SDK and re-exports the manual API. Choose the package that matches the runtime; do not copy both imports into one file.

```ts
import * as logfire from '@pydantic/logfire-node'
```

```ts
import * as logfire from '@pydantic/logfire-browser'
```

Use `logfire` directly when OpenTelemetry is configured by the platform or another runtime package:

```ts
import * as logfire from 'logfire'
```

Cloudflare Workers use both imports when they need handler wrapping and manual spans:

```ts
import * as logfire from 'logfire'
import { instrument } from '@pydantic/logfire-cf-workers'
```

## Logs

Log helpers create point-in-time Logfire events. The second argument is structured attributes; use it for anything the user should be able to search or query.

```ts
logfire.trace('cache lookup {cache_key}', { cache_key })
logfire.debug('provider response received', { provider, status })
logfire.info('order created {order_id}', { order_id })
logfire.notice('plan upgraded {tenant}', { tenant })
logfire.warning('retrying provider call', { provider, attempt })
logfire.error('payment failed', { payment_id, provider })
logfire.fatal('worker cannot start', { service: 'billing-worker' })
```

Do not flatten useful attributes into interpolated strings:

```ts
// Avoid
logfire.info(`order created ${orderId}`)

// Prefer
logfire.info('order created {order_id}', { order_id: orderId })
```

## Spans

Prefer the current options-object form. `span()` auto-closes after the callback resolves or throws, records thrown errors on the span, and preserves the callback result.

```ts
await logfire.span('process order {order_id}', {
  attributes: { order_id: orderId },
  callback: async () => {
    const items = await fetchItems(orderId)
    logfire.info('fetched order items', { count: items.length })
    return processItems(items)
  },
})
```

Use `startSpan()` only when the lifetime cannot be expressed as a callback:

```ts
const span = logfire.startSpan('run job {job_id}', { job_id: jobId })
try {
  await runJob(jobId)
} finally {
  span.end()
}
```

Use `startPendingSpan()` for long-running operations that should appear in Logfire immediately:

```ts
const span = logfire.startPendingSpan('load dashboard', { route: '/dashboard' })
try {
  await loadDashboard()
} finally {
  span.end()
}
```

Pass `parentSpan` only when explicit parentage is required outside normal async context propagation.

## Function Instrumentation

Use `instrument(fn, options)` when wrapping a reusable function is cleaner than editing its body.

```ts
const fetchCustomer = logfire.instrument(fetchCustomerImpl, {
  message: 'fetch customer {customer_id}',
  extractArgs: ['customer_id'],
  tags: ['customers'],
})

await fetchCustomer('cus_123')
```

Prefer explicit `extractArgs: ['name']`. Avoid `extractArgs: true` in production code that may be bundled or minified. Use `recordReturn: true` sparingly and only for non-sensitive, bounded values.

## Errors

Use `reportError()` from explicit catch blocks. The caught value can be `unknown`.

```ts
try {
  await syncCustomer(customerId)
} catch (error) {
  logfire.reportError('customer sync failed', error, { customer_id: customerId }, { tags: ['customers'] })
  throw error
}
```

`reportError()` is the JavaScript API; there is no Python-style `exception()` helper.

## Scoped Clients And Tags

Use `withTags()` or `withSettings()` when several calls share stable defaults.

```ts
const payments = logfire.withTags('payments')

payments.info('payment authorized {payment_id}', { payment_id })

await payments.span('capture payment {payment_id}', {
  attributes: { payment_id },
  callback: async () => capturePayment(paymentId),
})
```

Per-call tags are merged with scoped tags. Tags should identify stable subsystems or workflows, not high-cardinality user data.

## Configuration Options

Runtime `configure()` calls accept common manual API options such as `minLevel`, `baggage`, `jsonSchema`, `scrubbing`, and `sampling`.

```ts
logfire.configure({
  serviceName: 'checkout-api',
  environment: process.env.NODE_ENV,
  minLevel: 'info',
  scrubbing: {
    extraPatterns: ['secret_token'],
  },
  baggage: {
    spanAttributes: ['tenant', 'region'],
  },
})
```

Keep baggage allowlists small and stable. Do not put secrets, session cookies, raw emails, or access tokens in baggage or span attributes.

## Sampling

Use head sampling for broad volume reduction:

```ts
logfire.configure({
  serviceName: 'checkout-api',
  sampling: { head: 0.1 },
})
```

Use tail sampling when errors or slow traces must be kept:

```ts
logfire.configure({
  serviceName: 'checkout-api',
  sampling: logfire.levelOrDuration({
    durationThreshold: 2.0,
    levelThreshold: 'warning',
  }),
})
```

Be conservative with tail sampling in browsers and long-lived processes because it buffers spans.
