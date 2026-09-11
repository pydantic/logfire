---
title: "See Monty sandbox execution in Logfire"
description: "Record code execution, host calls, errors, and pool health from Pydantic Monty."
integration: logfire
---
# Pydantic Monty

See what code does inside a [Pydantic Monty](https://github.com/pydantic/monty) sandbox, including
its inputs, result, host calls, printed output, errors, and time spent running or waiting on the
host.
Logfire groups one checkout into a **trace** (the full journey of one request, made of nested spans).
Each session, code run, and host round trip is a **span** (one unit of work: a single operation, with
a name, a start, and a duration).

## What you'll capture

- Each checkout as a session span
- Each code run, including the Python source, inputs, result, and execution time
- Calls from the sandbox to host functions and operating-system handlers, including arguments and results
- Printed output, typing errors, and runtime errors
- **Metrics** (numbers tracked over time) for worker counts, checkout waits, worker terminations,
  session duration, run duration, and execution time

!!! warning "Sandbox content is sent to Logfire"
    Instrumentation records Python source, inputs, outputs, host-call arguments and results, exceptions,
    and printed text. These values may contain personal or proprietary data. Logfire applies its standard
    [scrubbing](../how-to-guides/scrubbing.md) before sending data, and Monty limits each recorded value to
    64 KiB.

{{ before_you_start() }}

## Install Logfire and Monty

Install `logfire`:

{{ install_logfire() }}

Install Monty:

```bash
pip install pydantic-monty
```

## Record sandbox execution

Call [`logfire.instrument_monty()`][logfire.Logfire.instrument_monty] after configuring Logfire and
before creating a Monty pool:

```python title="main.py" hl_lines="6"
from pydantic_monty import Monty

import logfire

logfire.configure()
logfire.instrument_monty()

with Monty() as pool:
    with pool.checkout(script_name='calculation.py') as session:
        result = session.feed_run('sum([20, 21, 1])')
        assert result == 42
```

The integration supplies Monty with OpenTelemetry-compatible tracing, logging, and metrics components
bound to the configured Logfire instance. The same components work for synchronous and asynchronous pools
throughout the process. Calling `logfire.instrument_monty()` more than once has no additional effect.

## Verify it worked

Run `python main.py`, then open the [Live view](../guides/web-ui/live.md).
You should see a `session calculation.py` span containing a `run code` span with the source, result,
and duration.

Open the Metrics view to query measurements such as `monty.pool.workers.live` and
`monty.run.duration`.
Metrics cover every checkout and use fixed, low-cardinality attributes, so sandbox code cannot create
new time series by choosing function names, paths, or exception classes. Monty records each measurement
through Logfire's configured metrics pipeline, including custom [`MetricsOptions`][logfire.MetricsOptions]
views and additional readers.

## Troubleshoot missing data

- **`instrument_monty()` reports that OpenTelemetry instrumentation is unavailable:** upgrade
  `pydantic-monty` to a release that includes `instrument_telemetry()`.
- **No session spans appear:** call `logfire.instrument_monty()` before the first checkout.
- **Spans appear but pool metrics do not:** create the Monty pool after calling
  `logfire.instrument_monty()`. Pool-wide metrics are connected when the pool is created.
- **No data appears in Logfire:** check that your write token is set. Run
  `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN` environment variable in
  production. See [Getting Started](../index.md).
