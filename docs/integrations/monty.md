---
title: "See Monty sandbox execution in Logfire"
description: "Record code execution, host calls, errors, and pool health from Pydantic Monty."
integration: logfire
---
# Pydantic Monty

See what code does inside a [Pydantic Monty](https://github.com/pydantic/monty) sandbox, including
its inputs, result, host calls, printed output, errors, and time spent running or waiting on the
host.
Each checkout (borrowing a sandbox worker from the pool) creates a session **span** (one unit of work:
a single operation, with a name, a start, and a duration), with nested spans for code runs and host calls.
If your application already has a current span, the session joins its **trace** (the full journey of
one request, made of nested spans). Otherwise, it starts a new trace.

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

Both synchronous and asynchronous pools use the same process-wide integration. The first call selects
the Logfire instance and its instance-specific settings, such as tags set with
[`with_settings()`][logfire.Logfire.with_settings]. Later calls do not replace them.

## Verify it worked

Run `python main.py`, then open the [Live view](../guides/web-ui/live.md).
You should see a `session calculation.py` span containing a `run code` span with the source, result,
and duration.

Open the Metrics view to query measurements such as `monty.pool.workers.live` and
`monty.run.duration`.
Metrics cover every checkout and use a fixed set of labels, so sandbox code cannot create
new time series by choosing function names, paths, or exception classes.
Custom metric aggregation and collection settings in [`MetricsOptions`][logfire.MetricsOptions] also apply.

## Troubleshoot missing data

- **`instrument_monty()` reports that OpenTelemetry instrumentation is unavailable:** upgrade
  `pydantic-monty` to a release that includes `instrument_telemetry()`.
- **Tool spans appear outside the corresponding Monty call:** nesting spans created inside host
  functions requires Monty's callback context propagation, which is not available in Monty 0.0.23.
  Without it, those spans follow the caller's tracing context (the parent span used for new spans).
  Manual dispatch through `feed_start()` and `snapshot.resume()`, including the current
  Pydantic AI Harness `CodeMode` implementation, also needs explicit context propagation to nest
  host-function spans. Calling `logfire.instrument_monty()` alone does not provide it.
- **No session spans appear:** call `logfire.instrument_monty()` before the first checkout.
- **Spans appear but pool metrics do not:** create the Monty pool after calling
  `logfire.instrument_monty()`. Pool-wide metrics are connected when the pool is created.
- **No data appears in Logfire:** check that your write token is set. Run
  `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN` environment variable in
  production. See [Getting Started](../index.md).
