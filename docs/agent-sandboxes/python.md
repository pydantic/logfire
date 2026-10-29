---
title: "Run agent code in Agent Sandboxes from Python"
description: "Install the Logfire SDK, create an API key, and run code in Logfire Agent Sandboxes."
---

# Run code from Python

!!! info "Experimental"
    Agent Sandboxes is experimental and available to selected Logfire organizations. Email
    [engineering@pydantic.dev](mailto:engineering@pydantic.dev) if you want to try it.

Run Python in a remote [Agent Sandbox](index.md) from your application, with one call to
[`logfire.agent_sandboxes()`][logfire.Logfire.agent_sandboxes].
You check out a session, send it code, and get the result back.

## Before you start

You need [access to Agent Sandboxes](index.md) in your organization.

### Enable Agent Sandboxes

First, open **AI Optimization** > **Agent Sandboxes** in your project.
If you see **Enable Agent Sandboxes**, ask a project manager to select it.
An execution key does not enable the project by itself.

For a new project, you can also start from product onboarding:

1. Choose **Me** or **My team** under **Who are you setting up Logfire for?**
2. Select **Use Agent Sandboxes** under **What do you want to do first?**

<img src="/logfire/images/guide/agent-sandboxes/onboarding-sandboxes.webp" alt="Product onboarding with Use Agent Sandboxes among the setup choices" width="672" height="490" loading="lazy" />

Logfire enables Agent Sandboxes for the project, adds a sidebar favorite, and opens **Setup**.
This choice does not create an execution key or run code.
Your account still needs permission to enable the project.
The organization's enabled-project limit also applies.

### Get an execution key

You also need a Logfire API key with permission to run code in your project's agent sandboxes
(`project:execute_agent_sandboxes`):

1. Open **AI Optimization** > **Agent Sandboxes** and select **Setup**.
2. Under **Choose an execution key**, select **Create execution key**.
3. Copy the key.
   It won't be shown again.

<img src="/logfire/images/guide/agent-sandboxes/connect-key.webp" alt="Setup with a Workbench link and the Choose an execution key step showing key creation and existing-key options" width="768" height="222" loading="lazy" />

*The setup page offers key creation or use of an existing key.*

You can also create the key in **Project settings → Security & access → API keys → New API key**. Open **Advanced** and
select **Run code in this project's agent sandboxes**.

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
The pool opens a connection when you call `pool.checkout()`, which gives you a session with its own sandbox.
`session.feed_run()` executes the submitted snippet. The pool also supports step-by-step execution with `feed_start()`.

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

from pydantic_monty import CollectString

import logfire

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

The hosted runtime records each session and code run as a **span** (one unit of work, with a name, start, and duration).
`logfire.agent_sandboxes()` sends the current trace context with each connection.
If your application has a current span, the hosted sandbox spans join its **trace**, the full journey of one request.
You do not need to call `logfire.instrument_monty()` for hosted sandbox activity.

!!! warning "Sandbox content is recorded in your project"
    Hosted telemetry can include your code, inputs, result, host function arguments and results, and printed output.
    Client [scrubbing](../how-to-guides/scrubbing.md) does not redact execution requests or saved session state.
    See [tracing and storage](limits.md#understand-tracing-and-storage) before you submit sensitive data.

To record Monty execution on your own machines, see [Trace local Monty sandboxes](../integrations/monty.md).

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

- **`LogfireConfigError: Agent sandboxes require a Logfire API key`**: no API key was found.
  Set `LOGFIRE_API_KEY`, pass `api_key` to `logfire.configure()`, or pass `api_key` to `logfire.agent_sandboxes()`.
- **`RuntimeError: failed to spawn monty worker: ...
  HTTP error: 401 Unauthorized`**: the server rejected the API key.
  Check that the key is correct, hasn't been deleted, and has permission to run code in this project's agent sandboxes.
- **`RuntimeError: logfire.agent_sandboxes() requires the pydantic-monty-client package`**: install Logfire with the
  extra: `pip install 'logfire[agent-sandboxes]'`.
- **`MontyCrashedError` with `timed_out=True`**: the call took longer than `request_timeout`.
  Pass a larger `request_timeout` to `logfire.agent_sandboxes()`.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): continue a session later, take snapshots, and branch sessions.
- [Agent Sandboxes overview](index.md): when to use sandboxes, and when not to.
- [Trace local Monty sandboxes](../integrations/monty.md): run Monty on your own machine instead.
- [Scrubbing](../how-to-guides/scrubbing.md): control which values are hidden before data is sent.
