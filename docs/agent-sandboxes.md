---
title: Agent Sandboxes
description: Run untrusted agent code in Logfire Agent Sandboxes from Node.js with @pydantic/logfire-agent-sandboxes.
---

# Agent Sandboxes

Logfire Agent Sandboxes run Python code that your agents write in isolated, remote
[Pydantic Monty](https://pydantic.dev/docs/monty/) sandboxes hosted by Logfire, and send the result back to your
application. The code never runs in your process, and it can reach the outside world only through the host functions
you pass to it.

`@pydantic/logfire-agent-sandboxes` connects to them from Node.js. It returns a `MontyRemote` pool from
`@pydantic/monty` that is already set up with your API key, your Logfire region, and the current trace context.

## Before you start

You need a Logfire project API key with the **Run code in this project's agent sandboxes** permission
(`project:execute_agent_sandboxes`). In your project, open **Agent Sandboxes**, click **Setup**, and click
**Create execution key** on the **Set up Agent Sandboxes** page. To use a key you already have, give it that permission
under **Settings → API Keys** instead. Agent Sandboxes reject personal API keys.

Set it as the `LOGFIRE_API_KEY` environment variable where your application runs:

```bash
export LOGFIRE_API_KEY='your-api-key'
```

The key also selects the data region your sandboxes run in, so you don't need to configure a URL.

## Install

```bash
npm install @pydantic/logfire-agent-sandboxes @pydantic/monty@^1.5.0
```

`@pydantic/monty` is a peer dependency. Version 1.5.0 or later is required, because Logfire serves Agent Sandboxes over gRPC and that is the first version with the gRPC client. Import sessions, session errors, and helpers such as `CollectString` from it directly.

## Run your first snippet

```ts
import { agentSandboxes } from '@pydantic/logfire-agent-sandboxes'

await using pool = await agentSandboxes()
await using session = await pool.checkout()
console.log(await session.feedRun('sum([20, 21, 1])')) // 42
```

No connection is made until `pool.checkout()`, which gives you a session with its own sandbox. Variables and functions
defined in one `feedRun()` call are available in later calls on the same session.

`await using` is JavaScript's
[explicit resource management](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/await_using),
supported in Node.js 24 and TypeScript 5.2 and later. It works like Python's `async with`: when the enclosing block
exits, normally or by an exception, JavaScript awaits the value's `Symbol.asyncDispose` method. For a session, that
returns its sandbox to the pool. For the pool, it closes the pool. Values are disposed in reverse order, so the session
closes before the pool. The `await` is for that cleanup, not for creating the value: `await agentSandboxes()` and
`await pool.checkout()` are separate awaits on the right-hand side. Without `await using`, close them in `finally`:

```ts
const pool = await agentSandboxes()
try {
  const session = await pool.checkout()
  try {
    console.log(await session.feedRun('sum([20, 21, 1])'))
  } finally {
    await session.close()
  }
} finally {
  await pool.close()
}
```

## Let sandbox code call your functions

Pass your own functions in `externalLookup`. Sandbox code calls them by name, and each call runs in your application.
This is the only way sandbox code can reach anything outside the sandbox, so expose only the functions the code needs.

```ts
import { agentSandboxes } from '@pydantic/logfire-agent-sandboxes'
import { CollectString } from '@pydantic/monty'

const output = new CollectString()
await using pool = await agentSandboxes()
await using session = await pool.checkout()
const result = await session.feedRun("print('Checking the weather')\nget_weather('London')", {
  externalLookup: { get_weather: (city: string) => `Sunny in ${city}` },
  printCallback: output,
})
console.log(result) // Sunny in London
console.log(output.output) // Checking the weather
```

Host functions can also be `async`.

## Persist, snapshot, and fork sessions

Sessions are saved by the server under `session.sessionId` when the connection closes, unless you check them out with
`pool.checkout({ ephemeral: true })`. To continue from saved state, call `session.loadSession(id)` on a new session.
`session.dump()` returns a snapshot ID you can load the same way, and loading one ID in several sessions forks it into
independent branches. Saved sessions and snapshots are kept for 7 days.

## Use with the Vercel AI SDK

An agent can write one Python program that calls its tools, instead of calling them one model turn at a time.
`codeMode()` from `@pydantic/logfire-ai-sdk-code-mode` turns AI SDK tools into typed async Python functions in a sandbox
session and gives the model one `run_code` tool to call them from.

```bash
npm install @pydantic/logfire-ai-sdk-code-mode ai zod
```

```ts
import type { LanguageModel } from 'ai'

import { codeMode } from '@pydantic/logfire-ai-sdk-code-mode'
import { generateText, stepCountIs, tool } from 'ai'
import { z } from 'zod'

const getWeather = tool({
  description: 'Get the weather for a city.',
  inputSchema: z.object({ city: z.string() }),
  outputSchema: z.object({ city: z.string(), forecast: z.string() }),
  execute: async ({ city }) => ({ city, forecast: 'Sunny' }),
})

export async function askAgent(model: LanguageModel, prompt: string): Promise<string> {
  await using code = codeMode({ tools: { get_weather: getWeather } })
  const { text } = await generateText({
    model,
    prompt,
    tools: code.tools,
    // The default is one step, which ends the run before the model sees the result of run_code.
    stopWhen: stepCountIs(10),
  })
  return text
}
```

The model sees the tools only as Python signatures in the `run_code` description, so do not also pass them to
`generateText`. Tools that should stay direct can be spread in next to `code.tools`. Give each tool an `outputSchema`,
so the model knows what a call returns. Sandbox code chooses the arguments, so define tool schemas with zod 4.6.6 or
later: earlier versions validate every element of an oversized array before checking its length
([GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)).

One `codeMode()` object is one sandbox session, kept like a REPL for every `run_code` call it serves, so create one per
agent run. The session joins the trace that is active when you call `codeMode()`.

`codeMode()` is synchronous and starts nothing: it checks out the session on the first `run_code` call, from
`agentSandboxes()` unless you pass `sandboxes`. `await using code = codeMode(...)` only means that when `askAgent`
returns or throws, JavaScript awaits `code[Symbol.asyncDispose]()`, which closes the session, and the pool too if
`codeMode()` created it. It is the same as calling `await code.close()` in a `finally` block:

```ts
const code = codeMode({ tools: { get_weather: getWeather } })
try {
  const { text } = await generateText({ model, prompt, tools: code.tools, stopWhen: stepCountIs(10) })
  return text
} finally {
  await code.close()
}
```

With `streamText`, the function returns before the stream is read, so a block-scoped close would end the session too
early. Call `code.closeWhenDone(result)` instead, which closes once the stream finishes, fails or is aborted. A session
also ends after `idleTimeout` milliseconds without a call (default 300,000, five minutes).

Calling a tool from the sandbox skips the AI SDK's own approval and context handling, so `codeMode()` takes them as
options:

- `context`: each tool's context, keyed by tool name, as `toolsContext`.
- `approval`: the same shape as `toolApproval`, without the `'user-approval'` status, because nothing in the sandbox
  can wait for a person. An async function can ask one itself and return `'approved'` or `'denied'`, within
  `limits.timeout`. Tools with `needsApproval` are rejected.
- Sandbox code gets what `execute` returns, so a tool with `toModelOutput` is rejected rather than having its
  filtering bypassed.
- `limits`: a wall-clock `timeout` per snippet that includes time spent waiting on tools (in milliseconds, default 30,000), and caps
  on nested calls, concurrent calls, and the sizes of code, results and tool input and output.
- `onToolError`: replaces a tool's error message before the sandbox, the model or a span sees it. Messages pass through
  unchanged by default. A result that has no JSON form, such as a bigint or a cycle, is not a tool error, so it does not
  go through `onToolError`.
- A tool result is sent to the sandbox as JSON. A `Map` becomes a dict and a `Set` becomes a list.

If you pass your own `sandboxes`, set its `requestTimeout` above `limits.timeout`, so that a long snippet gets the
time-limit message instead of a dropped connection. `requestTimeout` is in seconds and `limits.timeout` is in
milliseconds: with the default `limits.timeout` of 30,000, `requestTimeout` must be above 30. `codeMode()` sets
`limits.timeout / 1000 + 10` for the pool it creates.

[`examples/agent-sandboxes-ai-sdk`](https://github.com/pydantic/logfire-js/tree/main/examples/agent-sandboxes-ai-sdk)
is a complete agent over a larger data set, with a smoke test.

## Tracing

Each checkout sends the trace context that is active when you call `pool.checkout()`, so the spans Logfire records for
the session join your application's trace. This works with any OpenTelemetry setup that registers a W3C trace context
propagator, including [`@pydantic/logfire-node`](https://pydantic.dev/docs/logfire/instrument/typescript/packages/node/).

The code you run, its inputs, host function arguments and results, and printed output are sent to Logfire's servers to
be executed. Session state is stored for up to 7 days unless the session is ephemeral.

## Options

`agentSandboxes()` accepts every `MontyRemote` pool option, plus:

| Option   | Default                                             | Description                                                                       |
| -------- | --------------------------------------------------- | --------------------------------------------------------------------------------- |
| `apiKey` | `LOGFIRE_API_KEY`                                   | API key with the `project:execute_agent_sandboxes` scope.                         |
| `url`    | `https://<region host>`, or from `LOGFIRE_BASE_URL` | `https://` or `http://` URL of the sandboxes server, no path, query, or fragment. |

The most common pool options:

- `maxProcesses`: the maximum number of sessions open at once (defaults to the number of CPUs). Further checkouts wait.
- `checkoutTimeout`: seconds `checkout()` waits for a free slot before rejecting. Defaults to waiting forever.
- `requestTimeout`: the maximum number of seconds for one call, such as `feedRun()` (default 10). Logfire requires a
  finite value; do not pass `null`.
- `metadata`: a function that returns extra gRPC request metadata (headers) for each checkout. Its entries are merged
  over the Logfire `authorization` entry and win on conflicts. Names are matched case-insensitively. `connectHeaders`,
  its former name, still works but is deprecated.

## Troubleshooting

The package exports `AgentSandboxError` for SDK configuration errors and as the base class for
`AgentSandboxRefusedError` and `AgentSandboxConnectionError`. Refused checkouts expose `statusCode`, `statusMessage`,
and `reason`, with the original `MontyRefusedError` on `cause`. Other pool creation or checkout failures raise
`AgentSandboxConnectionError`, with the message `Agent Sandboxes could not connect to <url>: <inner message>` and
the original error on `cause`. Errors from operations on a checked-out session pass through unchanged.

- **``AgentSandboxError: Agent Sandboxes require a Logfire API key with the `project:execute_agent_sandboxes` scope.``**:
  no API key was found. Set `LOGFIRE_API_KEY` or pass `apiKey`.
- **`AgentSandboxRefusedError: Agent Sandboxes refused the session: unauthenticated`**: the server rejected the API
  key. Use a project API key, not a personal key, with the **Run code in this project's agent sandboxes** permission
  (`project:execute_agent_sandboxes`). Check that the key is correct, hasn't been deleted, matches the URL's region,
  and that Agent Sandboxes are enabled for the project. The same checks apply to `PERMISSION_DENIED`.
- **`AgentSandboxError: Agent Sandboxes URL must use http://<host> or https://<host> with no path, query or fragment.`**:
  `url` or `LOGFIRE_BASE_URL` is invalid. Remove any path, including the old `/monty-ws/` path, query, or fragment.
  Pass only the scheme and host, such as `https://logfire-us.pydantic.dev`.
- **`MontyCrashedError` with `timedOut: true`**: the call took longer than `requestTimeout`. Pass a larger finite value.
