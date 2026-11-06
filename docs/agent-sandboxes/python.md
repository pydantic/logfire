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

If you received an invitation link, open it first.
The link turns on the **Agent Sandboxes** page in your browser.

Then open **AI Optimization** > **Agent Sandboxes** in your project.
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

You also need a non-personal project API key with permission to run code in your project's agent sandboxes
(`project:execute_agent_sandboxes`). The setup page creates the required key type:

1. Open **AI Optimization** > **Agent Sandboxes** and select **Setup**.
2. Under **Choose an execution key**, select **Create execution key**.
3. Copy the key.
   It won't be shown again.

Only project administrators can create a key here.
Keys created on the setup page expire after 30 days, or sooner if your organization limits key lifetime.

<img src="/logfire/images/guide/agent-sandboxes/connect-key.webp" alt="Setup page with the Choose an execution key step, showing Create execution key, Use existing key, and View API keys" width="620" height="180" loading="lazy" />

*The setup page offers key creation or use of an existing key.*

You can also create the key in **Project settings → Security & access → API keys → New API key**. Open **Advanced** and
select **Run code in this project's agent sandboxes**.
Under **Ownership**, choose **Service**. Personal keys cannot run sandbox code.
Ask a project administrator to create it if your role only permits personal keys.
See [Project API keys](../reference/advanced/use-api-keys.md#project-api-key).

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
`session.feed_run()` executes the submitted snippet. The session also supports step-by-step execution with `feed_start()`.

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
Expose only the functions the code needs.
Mounted [volume files](volumes.md) are another source of data when volume access is enabled.

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

`logfire.agent_sandboxes()` accepts the same pool options as Monty's [`AsyncMontyWebsocket`][pydantic_monty.AsyncMontyWebsocket].
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

## Handle checkout errors

If a checkout fails, `pool.checkout()` raises one of two Logfire errors. Catch them around the checkout:

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

Both errors inherit from `logfire.AgentSandboxError`. Catch the base class to handle either checkout failure.

Every server refusal raises `AgentSandboxRefusedError`, including a refusal without a troubleshooting hint.
Its `status_code`, `status_message`, and `reason` attributes copy the `status_code`, `status_message`, and `cause`
of the original `MontyRefusedError`.
Authentication and capacity refusals include a Logfire hint on a separate line.

The original exception is kept as `exc.__cause__`. For example, the exception chain of a capacity refusal ends with:

```text
pydantic_monty.MontyRefusedError: failed to spawn monty worker: https://logfire-us.pydantic.dev: RESOURCE_EXHAUSTED: server at capacity

The above exception was the direct cause of the following exception:

logfire.exceptions.AgentSandboxRefusedError: Agent Sandboxes refused the session: server at capacity
Logfire Agent Sandboxes: Lower `max_processes` to open fewer sessions at once, or retry after a delay.
```

A connection failure raises `AgentSandboxConnectionError`.
Examples are an unreachable address, a connection timeout, a failed TLS handshake, or a server that does not support gRPC.
The exception chain of a connection timeout ends with:

```text
RuntimeError: failed to spawn monty worker: https://logfire-us.pydantic.dev: connect timed out after 10s

The above exception was the direct cause of the following exception:

logfire.exceptions.AgentSandboxConnectionError: Agent Sandboxes could not connect to https://logfire-us.pydantic.dev: connect timed out after 10s
```

Errors inside a checked-out session pass through unchanged.
These include exceptions from your sandbox code, `MontyCrashedError`, `MontyDisconnectError`, and `MontyShutdown`.
Programming errors also pass through unchanged, such as invalid metadata or an exception from your metadata callback.

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
- **`AgentSandboxRefusedError: Agent Sandboxes refused the session: ...` with an authentication hint**:
  the server rejected the API key.
  Use a project API key, not a personal key.
  Check its `project:execute_agent_sandboxes` scope and the server region.
  Also check that Agent Sandboxes are enabled for the project.
- **`AgentSandboxRefusedError` with `reason` set to `caller_cap` or `capacity`**: too many sessions are open.
  Lower `max_processes` to open fewer sessions at once, or retry after a delay.
  The SDK does not retry refusals for you.
- **`AgentSandboxConnectionError: Agent Sandboxes could not connect to ...`**: check the URL, network access, and TLS
  configuration.
  Use the server origin without a path, query, or fragment.
  Inspect `__cause__` for the original connection diagnostic.
- **`RuntimeError: logfire.agent_sandboxes() requires the pydantic-monty-client package`**: install Logfire with the
  extra: `pip install 'logfire[agent-sandboxes]'`.
- **`MontyCrashedError` with `timed_out=True`**: the call took longer than `request_timeout`.
  Pass a larger `request_timeout` to `logfire.agent_sandboxes()`.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): continue a session later, take snapshots, and branch sessions.
- [Agent Sandboxes overview](index.md): when to use sandboxes, and when not to.
- [Trace local Monty sandboxes](../integrations/monty.md): run Monty on your own machine instead.
- [Scrubbing](../how-to-guides/scrubbing.md): control which values are hidden before data is sent.
