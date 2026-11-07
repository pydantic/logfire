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

## Handle Agent Sandboxes checkout errors

For remote sessions created by `logfire.agent_sandboxes()`, catch the public Logfire errors
around `pool.checkout()`. Install the client with `pip install 'logfire[agent-sandboxes]'` and
set `LOGFIRE_API_KEY` to a [non-personal project API key](../reference/advanced/use-api-keys.md#project-api-key)
with the `project:execute_agent_sandboxes` scope. Personal API keys cannot execute Agent Sandboxes sessions.
The key's region must match the server URL, and Agent Sandboxes must be enabled for the project.

```python skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

logfire.configure()


async def main():
    async with logfire.agent_sandboxes() as pool:
        try:
            async with pool.checkout() as session:
                result = await session.feed_run('1 + 1')
                print(result)
        except logfire.AgentSandboxRefusedError as exc:
            print(exc.status_code, exc.status_message, exc.reason)
        except logfire.AgentSandboxConnectionError as exc:
            print(exc)


asyncio.run(main())
```

Both errors inherit from `logfire.AgentSandboxError`, so you can catch that base class to handle
either checkout failure. Every server refusal raises `AgentSandboxRefusedError`, including
refusals without a troubleshooting hint. Its `status_code`, `status_message`, and `reason`
attributes copy the original `MontyRefusedError`'s `status_code`, `status_message`, and `cause`.
Authentication and capacity refusals include a Logfire hint on a separate line.

The original exception is preserved as `exc.__cause__`. For example, a capacity refusal's
exception chain ends with:

```text
pydantic_monty.MontyRefusedError: failed to spawn monty worker: https://logfire-us.pydantic.dev: RESOURCE_EXHAUSTED: server at capacity

The above exception was the direct cause of the following exception:

logfire.exceptions.AgentSandboxRefusedError: Agent Sandboxes refused the session: server at capacity
Logfire Agent Sandboxes: Lower `max_processes` to open fewer sessions at once, or retry after a delay.
```

Connection failures, such as an unreachable address, connection timeout, failed TLS (Transport
Layer Security) handshake, or a server that does not support gRPC (a protocol for calling functions
on a remote server), raise
`AgentSandboxConnectionError`. A connection timeout's exception chain ends with:

```text
RuntimeError: failed to spawn monty worker: https://logfire-us.pydantic.dev: connect timed out after 10s

The above exception was the direct cause of the following exception:

logfire.exceptions.AgentSandboxConnectionError: Agent Sandboxes could not connect to https://logfire-us.pydantic.dev: connect timed out after 10s
```

Errors inside a checked-out session pass through unchanged: this includes user-code exceptions,
`MontyCrashedError`, `MontyDisconnectError`, and `MontyShutdown`. Programming errors such as
invalid metadata or exceptions from your metadata callback also pass through unchanged.

## Troubleshoot Agent Sandboxes checkout

- **`Agent Sandboxes refused the session: ...` with an authentication hint:** use a project API
  key, not a personal key. Check its `project:execute_agent_sandboxes` scope, the server region,
  and whether Agent Sandboxes are enabled for the project.
- **A `RESOURCE_EXHAUSTED` refusal with `reason` set to `caller_cap` or `capacity`:** lower `max_processes` to open
  fewer sessions at once, or retry after a delay. The SDK does not retry refusals for you.
- **`Agent Sandboxes could not connect to ...`:** check the URL, network access, and TLS
  configuration. Use the server origin without a path, query, or fragment. Inspect `__cause__`
  for the original connection diagnostic.

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
