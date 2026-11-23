---
title: "Celery integration"
description: "Instrument Celery with Logfire for distributed tracing."
---

# Celery integration

Logfire can automatically propagate tracing context across Celery workers. To enable this, **the instrumentation must be applied at import time**, before any Celery tasks are defined.

```python
import logfire
from celery import Celery

# Call this as early as possible – typically the first line of your entrypoint.
logfire.instrument_celery()

app = Celery("myapp", broker="redis://localhost:6379/0")

@app.task
def add(x: int, y: int) -> int:
    return x + y
```

## Why the top‑level call matters
The Logfire Celery integration registers a handler on the `celery.signals.worker_init` signal. If the call is made **after** tasks have been imported, the signal handler will miss the worker initialization, and context propagation will not work. This behavior is documented in the OpenTelemetry issue [#1002](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/1002#issuecomment-1275273134).

## Configuration
You can optionally configure the service name for the worker side:

```python
@celery.signals.worker_init.connect
def configure_worker(*_):
    logfire.configure(service_name="worker")
    # instrumentation is already active from the top‑level call
```

## Further reading
- [Logfire FastAPI integration](../integrations/fastapi.md)
- [OpenTelemetry Python Contrib – Celery](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation/celery)
