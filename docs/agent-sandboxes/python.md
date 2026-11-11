---
title: "Run agent code in Agent Sandboxes from Python"
description: "Install the Logfire SDK, create an API key, and run code in Logfire Agent Sandboxes."
---

# Run code from Python

!!! info "Beta"
    Agent Sandboxes is in beta on Logfire Cloud. If you do not see **Agent Sandboxes** in your project, see
    [Enable Agent Sandboxes](#enable-agent-sandboxes).

Run Python in a remote [Agent Sandbox](index.md) from your application, with one call to
[`logfire.agent_sandboxes()`][logfire.Logfire.agent_sandboxes].
You check out a session, send it code, and get the result back.

## Before you start

### Enable Agent Sandboxes

Agent Sandboxes is available to every Logfire Cloud organization, in the US and EU regions.
While it is in beta, the **Agent Sandboxes** page is hidden until you turn it on in your browser. Do one of these:

- Open the invitation link you received.
- Open the **Early access** settings page, show the experimental features, and turn on **Agent Sandboxes**.
- For a new project, start from product onboarding, as described below.

Then open **AI Runtime** > **Agent Sandboxes** in your project.
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

1. Open **AI Runtime** > **Agent Sandboxes** and select **Setup**.
2. Under **Choose an execution key**, select **Create execution key**.
3. Copy the key.
   It won't be shown again.

Only project administrators can create a key here.
Keys created on the setup page expire after 30 days, or sooner if your organization limits key lifetime.
These keys can also send telemetry, so the same `LOGFIRE_API_KEY` works for `logfire.configure()`.

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
When the session's `async with` block exits, the server saves its state under the session's ID.
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
Mounted [volume files](volumes.md) are another source of data.

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

`logfire.agent_sandboxes()` accepts the same pool options as Monty's [`AsyncMontyRemote`][pydantic_monty.AsyncMontyRemote].
It returns an `AsyncMontyRemote` pool.
The most common ones:

- `max_processes`: the maximum number of sessions open at once (defaults to the number of CPUs).
  Further checkouts wait.
- `checkout_timeout`: how many seconds `checkout()` waits for a free slot before raising `TimeoutError`.
  Defaults to waiting forever.
- `request_timeout`: the maximum number of seconds for one call, such as `feed_run()` (default 10).
  Raise it for long-running code. It must be a finite number of seconds.
- `api_key`: use a key other than `LOGFIRE_API_KEY`, or the `api_key` passed to
  [`logfire.configure()`][logfire.configure].

See [`logfire.agent_sandboxes()`][logfire.Logfire.agent_sandboxes] for every option.

## Handle checkout errors

`logfire.agent_sandboxes()` does not wrap Monty's exceptions. If the server refuses a session, `pool.checkout()` raises
`MontyRefusedError`:

```python skip-run="true" skip-reason="external-connection"
import asyncio

from pydantic_monty import MontyRefusedError

import logfire

logfire.configure()


async def main():
    async with logfire.agent_sandboxes() as pool:
        try:
            async with pool.checkout() as session:
                print(await session.feed_run('1 + 1'))
        except MontyRefusedError as exc:
            print(exc.status_code, exc.cause, exc.status_message)


asyncio.run(main())
```

No session existed when the server refused, so nothing ran, and you can safely retry.
`status_code` is the gRPC status, such as `UNAUTHENTICATED`, `PERMISSION_DENIED`, or `RESOURCE_EXHAUSTED`.
`cause` is the reason in `snake_case`, such as `unauthenticated`, `capacity`, or `caller_cap`.

If the client cannot reach the server, `checkout()` raises `RuntimeError`.
Examples are an unreachable address, a connection timeout, or a failed TLS handshake.

Errors inside a checked-out session also come from Monty.
These include exceptions from your sandbox code, `MontyCrashedError`, `MontyDisconnectError`, and `MontyShutdown`.

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
- **`MontyRefusedError` with `status_code` `UNAUTHENTICATED` or `PERMISSION_DENIED`**: the server rejected the API key.
  Use a project API key, not a personal key.
  Check its `project:execute_agent_sandboxes` scope and that the key's region matches the server.
  Also check that Agent Sandboxes are enabled for the project.
- **`MontyRefusedError` with `cause` `capacity` or `caller_cap`**: too many sessions are open.
  Lower `max_processes` to open fewer sessions at once, or retry after a delay.
  The SDK does not retry refusals for you.
- **`RuntimeError: failed to spawn monty worker: ...`**: the client could not connect.
  Check the URL, network access, and TLS configuration.
  Use the server origin, such as `https://logfire-us.pydantic.dev`, without a path, query, or fragment.
- **`LogfireConfigError` about the URL path**: remove the old `/monty-ws/` path from the `url` you pass.
- **`RuntimeError: logfire.agent_sandboxes() requires the pydantic-monty-client package`**: install Logfire with the
  extra: `pip install 'logfire[agent-sandboxes]'`.
- **`MontyCrashedError` with `timed_out=True`**: the call took longer than `request_timeout`.
  Pass a larger `request_timeout` to `logfire.agent_sandboxes()`.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): continue a session later, take snapshots, and branch sessions.
- [Agent Sandboxes overview](index.md): when to use sandboxes, and when not to.
- [Trace local Monty sandboxes](../integrations/monty.md): run Monty on your own machine instead.
- [Scrubbing](../how-to-guides/scrubbing.md): control which values are hidden before data is sent.
