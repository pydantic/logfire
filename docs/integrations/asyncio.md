---
title: "Logfire Asyncio Integration: Monitor Async Operations"
description: Learn how to use the OpenTelemetry asyncio instrumentation with Logfire to trace and monitor asyncio-based operations.
integration: otel
---
# Asyncio

The [OpenTelemetry Asyncio Instrumentation][opentelemetry-asyncio] package can be used with **Logfire** to trace
and monitor `asyncio`-based operations, such as coroutines and tasks.

Since **Logfire** is [OpenTelemetry][opentelemetry] compatible, you can use the `AsyncioInstrumentor` directly.

## Installation

Install the `opentelemetry-instrumentation-asyncio` package:

```bash
pip install opentelemetry-instrumentation-asyncio
```

## Usage

```py title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

import logfire

logfire.configure()
os.environ['OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE'] = 'my_coro'

AsyncioInstrumentor().instrument()


async def my_coro():
    await asyncio.sleep(0.1)


async def main():
    await asyncio.create_task(my_coro())


asyncio.run(main())
```

The `OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE` environment variable specifies which coroutine names
to trace. Set it to a comma-separated list of coroutine function names.

You can find more configuration options in the
[OpenTelemetry asyncio instrumentation documentation][opentelemetry-asyncio].

## Monitoring Slow Async Callbacks

Logfire also provides a built-in way to detect when functions running in the asyncio event loop block for too long.
Use [`logfire.log_slow_async_callbacks()`][logfire.Logfire.log_slow_async_callbacks] to log a warning whenever
a callback exceeds a specified duration:

```py title="main.py" skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.log_slow_async_callbacks(slow_duration=0.1)
```

This patches `asyncio.events.Handle._run` to measure execution time and logs a warning for any callback
that takes longer than `slow_duration` seconds (default: 0.1s).

[opentelemetry-asyncio]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncio/asyncio.html
[opentelemetry]: https://opentelemetry.io/
