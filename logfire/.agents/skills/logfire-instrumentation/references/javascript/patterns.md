# JavaScript / TypeScript Patterns

## Log Levels

From lowest to highest severity:

```typescript
logfire.trace('Detailed trace', { detail: x })
logfire.debug('Debug info', { state: s })
logfire.info('Normal operation', { event: e })
logfire.notice('Notable event', { event: e })
logfire.warn('Warning', { issue: i })
logfire.error('Error occurred', { error: err })
logfire.fatal('Fatal error', { error: err })
```

All methods accept `(message, attributes?, options?)`. Options can include `{ tags: ['tag1'] }`.

## Spans

### Callback-based (auto-closes)

```typescript
await logfire.span('Processing order', { order_id }, {}, async () => {
    const items = await fetchItems(order_id)
    logfire.info('Fetched items', { count: items.length })
    return processItems(items)
})
```

### Manual control

```typescript
const span = logfire.startSpan('Long operation', { job_id })
try {
    await doWork()
} finally {
    span.end()
}
```

Child spans reference their parent via the `parentSpan` option.

## Error Handling

```typescript
try {
    await processOrder(orderId)
} catch (error) {
    logfire.reportError('order processing', error)
    throw error
}
```

`reportError` automatically extracts stack traces and error details into structured span attributes.

## Configuration

### Environment variables

```bash
LOGFIRE_TOKEN=your-write-token
LOGFIRE_SERVICE_NAME=my-service
LOGFIRE_SERVICE_VERSION=1.0.0
```

### Programmatic

```typescript
logfire.configure({
    token: process.env.LOGFIRE_TOKEN,
    serviceName: 'my-service',
    serviceVersion: '1.0.0',
})
```
