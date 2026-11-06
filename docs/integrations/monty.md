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
  On macOS arm64, Monty 0.0.23 and 1.0.0 accept instrumentation but emit no session or run spans.
  This is [reported upstream](https://github.com/pydantic/monty/issues/1011). Use Linux if you need
  these spans with those releases.
- **Spans appear but pool metrics do not:** create the Monty pool after calling
  `logfire.instrument_monty()`. Pool-wide metrics are connected when the pool is created.
- **No data appears in Logfire:** check that your write token is set. Run
  `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN` environment variable in
  production. See [Getting Started](../index.md).

## Troubleshoot Agent Sandboxes

Use this section when `logfire.agent_sandboxes()` cannot open or
run a hosted sandbox. These checks do not apply to a local `Monty()` pool.

- **Authentication refusal:** a message such as
  `MontyRefusedError: failed to spawn monty worker: https://logfire-us.pydantic.dev: UNAUTHENTICATED: unauthenticated`,
  or a refusal with `PERMISSION_DENIED`, requires these checks. Use a **project API key**, not a
  personal key, with the `project:execute_agent_sandboxes` scope. Create it in
  **Project → Settings → API Keys**; see [API keys](../reference/advanced/use-api-keys.md).
  Check that the key's region matches the server URL and that Agent Sandboxes are enabled for
  the project. This message alone does not identify which check failed.
- **Capacity refusal:** `RESOURCE_EXHAUSTED: assignment attempt rate exceeded`, with `cause` set
  to `caller_cap` or `capacity`, means too many sessions opened at once or the service has no
  capacity. Lower `max_processes` in `logfire.agent_sandboxes()` or retry after a delay.
  The SDK does not retry for you.
- **Invalid URL:** for `a URL path, query or fragment is not supported`, use only the server
  origin, for example `https://logfire-us.pydantic.dev`. `/monty-ws/` was the old path; remove it.
  The SDK now checks both an explicit `url=` and a URL derived from Logfire configuration and
  raises `LogfireConfigError` before connecting.
- **Unbounded timeout:** for
  `RuntimeError: monty worker protocol error: CPU execution clock requires a finite client request_timeout`,
  do not pass `request_timeout=None`. Hosted sandboxes require a finite deadline. The SDK now
  raises `LogfireConfigError` up front for `None`. Omit the option to use Monty's default of
  10 seconds, or set a finite number of seconds.
- **`connect timed out`:** check the server URL, network access, and proxy settings. If the
  server is reachable but slow to open a session, increase the finite `request_timeout`.
- **`not a gRPC server`:** the URL reached a web page instead of the sandbox service. gRPC is
  the connection protocol Monty uses. Use the Logfire server origin for your region, without a
  path, and check that a proxy does not replace its response with a web page.
- **`MontyDisconnectError: connection closed while waiting for a reply`:** the connection ended
  after the session opened. Inspect the exception's `status_code`, `status_message`, and `cause`.
  The operation might already have run; do not retry operations with external effects unless
  you can safely repeat them.
- **`MontyShutdown`:** the server is shutting down. Keep `auto_resume=True` (the default) to
  resume stored sessions automatically. If you disable it, use the exception's `dump` when
  available to restore the session.

The SDK adds Logfire hints to authentication and capacity refusals. Because Monty's native
`MontyRefusedError` cannot be constructed or subclassed from Python, these hinted errors are
`RuntimeError` exceptions, chained from the original refusal. The cause retains `status_code`,
`status_message`, and `cause` for inspection. Other exceptions pass through unchanged.

### Check project execution limits

A sandbox `TimeoutError` or `MemoryError` can mean that code reached a project limit, not the
client's `request_timeout`. The default project limits are about **50 milliseconds of execution
time per feed** (one code submission) and **20 MiB of memory** (about 21 MB). A project admin can
adjust these limits. Asking for a larger limit in the client does not override the project's limit.
Reduce the work or memory needed for a submission, or ask a project admin to adjust the limit.

A single sandbox `time.sleep()` is capped at about **10 seconds** and can return before a longer
requested sleep finishes. Do not use one long sleep to wait for external work. Wait in host code
instead. Increasing `request_timeout` does not increase this sleep cap or the project limits.
