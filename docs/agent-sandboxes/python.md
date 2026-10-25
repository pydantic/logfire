---
title: "Run agent code in Agent Sandboxes from Python"
description: "Install the Logfire SDK, create an API key, and run code in Logfire Agent Sandboxes."
---

# Run code from Python

Run Python in a remote [Agent Sandbox](index.md) from your application, with one call to
[`logfire.agent_sandboxes()`][logfire.Logfire.agent_sandboxes].
You check out a session, send it code, and get the result back.

## Before you start

You need a Logfire API key with the **Run code in this project's agent sandboxes** permission
(`project:execute_agent_sandboxes`):

1. Open your project in Logfire.
2. Go to **Settings → API Keys → New API Key**.
3. Select **Run code in this project's agent sandboxes**, then create the key.
4. Copy the key.
   It won't be shown again.

Agent Sandboxes accept only project API keys that aren't
[personal](../reference/advanced/use-api-keys.md#personal-api-keys).
Organization API keys and personal keys are rejected.
Only organization and project admins can create a key that isn't personal.

Set it as the `LOGFIRE_API_KEY` environment variable where your application runs:

```bash
export LOGFIRE_API_KEY='your-api-key'
```

The key also selects the [data region](../reference/data-regions.md) your sandboxes run in, so you don't need to
configure a URL.
See [Use API keys](../reference/advanced/use-api-keys.md) for more about keys and permissions.

## Install Logfire with the `agent-sandboxes` extra

{{ install_logfire(extras=['agent-sandboxes']) }}

The extra installs `pydantic-monty-client`, the client for Pydantic Monty sandboxes.

## Run your first snippet

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

logfire.configure()


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            result = await session.feed_run('sum([20, 21, 1])')
            print(result)


asyncio.run(main())
```

Run `python main.py`.
It prints:

```
42
```

`logfire.agent_sandboxes()` returns a pool of sandboxes.
No connection is made until you call `pool.checkout()`, which gives you a session with its own sandbox.
Code runs only inside `session.feed_run()`.

## Keep state across runs

Variables and functions defined in one `feed_run()` call are available in later calls on the same session.
When the session's `async with` block exits, the server saves its state under `session.session_id`.
To continue from that state later, or to branch it into several sessions, see [Persist, resume, and fork
sessions](sessions.md).

```python skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

logfire.configure()


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            await session.feed_run('total = 40')
            result = await session.feed_run('total + 2')
            print(result)  # 42


asyncio.run(main())
```

## Let sandbox code call your functions

Pass your own functions in `external_lookup`.
Sandbox code can call them by name, and each call runs in your application, not in the sandbox.
This is the only way sandbox code can reach anything outside the sandbox, so expose only the functions the code needs.

```python skip-run="true" skip-reason="external-connection" hl_lines="19"
import asyncio

import logfire
from pydantic_monty import CollectString

logfire.configure()


def get_weather(city: str) -> str:
    return f'Sunny in {city}'


async def main():
    output = CollectString()
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            result = await session.feed_run(
                "print('Checking the weather')\nget_weather('London')",
                external_lookup={'get_weather': get_weather},
                print_callback=output,
            )
    print(result)  # Sunny in London
    print(output.output)  # Checking the weather


asyncio.run(main())
```

Host functions can also be `async def` functions.
`print_callback` collects what the sandbox code prints.
Without it, printed output goes to your application's standard output.

## See sandbox runs in Logfire

By default, `logfire.agent_sandboxes()` also calls [`logfire.instrument_monty()`][logfire.Logfire.instrument_monty], so
each session and each code run is recorded as a **span** (one unit of work: a single operation, with a name, a start,
and a duration).
If your application already has a current span, the sandbox spans join its **trace** (the full journey of one request,
made of nested spans).

!!! warning "Sandbox content is recorded in your project"
    With tracing on, Logfire records the code, its inputs and result, host function arguments and results, and printed
    output in your Logfire project.
    Logfire applies its standard [scrubbing](../how-to-guides/scrubbing.md) before sending data.

To turn tracing off, pass `instrument=False`:

```python skip-run="true" skip-reason="external-connection"
import logfire

pool = logfire.agent_sandboxes(instrument=False)
```

`instrument_monty()` applies to the whole process, and its first call wins.
If anything in your process has already called it, sandbox sessions are still traced.

## Configure the pool

`logfire.agent_sandboxes()` accepts the same pool options as Monty's `AsyncMontyWebsocket`.
The most common ones:

- `max_processes`: the maximum number of sessions open at once (defaults to the number of CPUs).
  Further checkouts wait.
- `checkout_timeout`: how many seconds `checkout()` waits for a free slot before raising `TimeoutError`.
  Defaults to waiting forever.
- `request_timeout`: the maximum number of seconds for one call, such as `feed_run()` (default 10).
  Raise it for long-running code, or pass `None` to wait indefinitely.
- `api_key`: use a key other than `LOGFIRE_API_KEY`, or the `api_key` passed to
  [`logfire.configure()`][logfire.configure].

See [`logfire.agent_sandboxes()`][logfire.Logfire.agent_sandboxes] for every option.

## Verify it worked

Run the [first snippet](#run-your-first-snippet).
It prints `42`.
Then open the [Live view](../guides/web-ui/live.md).
You should see a `session main.py` span with a `run code` span inside it, showing the code, the result, and how long it
took.

## Troubleshooting

- **`LogfireConfigError: Agent sandboxes require a Logfire API key with the project:execute_agent_sandboxes scope`**:
  no API key was found.
  Set `LOGFIRE_API_KEY`, pass `api_key` to `logfire.configure()`, or pass `api_key` to `logfire.agent_sandboxes()`.
- **`RuntimeError: failed to spawn monty worker: ...
  HTTP error: 401 Unauthorized`**: the server rejected the API key.
  Check that the key is correct, hasn't been deleted, and has the **Run code in this project's agent sandboxes**
  permission.
- **`RuntimeError: logfire.agent_sandboxes() requires the pydantic-monty-client package`**: install Logfire with the
  extra: `pip install 'logfire[agent-sandboxes]'`.
- **`MontyCrashedError` with `timed_out=True`**: the call took longer than `request_timeout`.
  Pass a larger `request_timeout` to `logfire.agent_sandboxes()`.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): continue a session later, take snapshots, and branch sessions.
- [Agent Sandboxes overview](index.md): when to use sandboxes, and when not to.
- [Trace local Monty sandboxes](../integrations/monty.md): run Monty on your own machine instead.
- [Scrubbing](../how-to-guides/scrubbing.md): control which values are hidden before data is sent.
