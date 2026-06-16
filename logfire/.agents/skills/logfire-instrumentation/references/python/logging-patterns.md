# Python Logging Patterns

## Log Levels

From lowest to highest severity:

```python
logfire.trace("Detailed trace {detail}", detail=x)
logfire.debug("Debug info {state}", state=s)
logfire.info("Normal operation {event}", event=e)
logfire.notice("Notable event {event}", event=e)
logfire.warn("Warning {issue}", issue=i)
logfire.error("Error occurred {error}", error=err)
logfire.fatal("Fatal error {error}", error=err)
```

## Nested Spans

Spans nest to create a tree visible in the Logfire UI. Use them to show the structure of an operation, not just that it happened:

```python
async def send_request(url: str):
    with logfire.span("HTTP request {method} {url}", method="POST", url=url):
        with logfire.span("Serialize payload"):
            payload = model.model_dump_json()
        with logfire.span("Send request"):
            response = await client.post(url, content=payload)
        logfire.info("Response {status}", status=response.status_code)
```

## Standard Library Logging Integration

For projects that already use Python's `logging` module, route existing log calls through Logfire rather than rewriting them all:

```python
from logging import basicConfig

import logfire

logfire.configure()
basicConfig(handlers=[logfire.LogfireLoggingHandler()])
```

Or with `dictConfig`:

```python
from logging.config import dictConfig

import logfire

logfire.configure()
dictConfig({
    'version': 1,
    'handlers': {
        'logfire': {'class': 'logfire.LogfireLoggingHandler'},
    },
    'root': {'handlers': ['logfire']},
})
```

## Suppressing Noisy Libraries

Some libraries emit excessive debug logs. Silence them at the `logging` level:

```python
import logging

logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
```

## Custom Metrics

For dashboards and alerting, create metrics:

```python
counter = logfire.metric_counter("orders_processed", unit="1")
counter.add(1, {"status": "success"})

histogram = logfire.metric_histogram("request_duration", unit="s")
histogram.record(0.123, {"endpoint": "/api/users"})

gauge = logfire.metric_gauge("active_connections")
gauge.set(42)
```

## Testing with capfire

Use the `capfire` pytest fixture to assert on emitted spans without sending data to production:

```python
from logfire.testing import CaptureLogfire

def test_order_processing(capfire: CaptureLogfire) -> None:
    process_order(order_id=123)

    spans = capfire.exporter.exported_spans_as_dict()
    assert any(
        span['attributes'].get('order_id') == 123
        for span in spans
    )
```

Configure logfire with `send_to_logfire=False` in test fixtures to prevent production data leakage.
