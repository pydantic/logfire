---
title: "Logfire Asyncio Integration: Monitor Async Operations"
description: Learn how to use logfire.instrument_asyncio() to trace and monitor asyncio-based operations.
integration: otel
---
# Asyncio

The [`logfire.instrument_asyncio()`][logfire.Logfire.instrument_asyncio] method can be used to instrument
`asyncio`-based operations with **Logfire**, including tracing coroutines, futures, and detecting slow
event loop callbacks.

## Installation

Install `logfire` with the `asyncio` extra:

{{ install_logfire(extras=['asyncio']) }}

## Usage

```py title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio
import os

import logfire

logfire.configure()
os.environ['OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE'] = 'my_coro'

logfire.instrument_asyncio()


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

## Slow Callback Detection

[`logfire.instrument_asyncio()`][logfire.Logfire.instrument_asyncio] also includes Logfire's built-in slow
callback detection. It logs a warning whenever a function running in the asyncio event loop blocks for
longer than `slow_duration` seconds (default: 0.1s):

```py title="main.py" skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_asyncio(slow_duration=0.5)
```

[`logfire.instrument_asyncio()`][logfire.Logfire.instrument_asyncio] uses the
**OpenTelemetry Asyncio Instrumentation** package,
which you can find more information about [here][opentelemetry-asyncio].

[opentelemetry-asyncio]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncio/asyncio.html
[opentelemetry]: https://opentelemetry.io/
