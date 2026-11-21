---
title: "Run agent code in Agent Sandboxes from TypeScript"
description: "Install the Logfire Agent Sandboxes package for Node.js, and run Python that your agent writes in a remote sandbox."
---

# Run code from TypeScript

!!! info "Beta"
    Agent Sandboxes is in beta on Logfire Cloud. If you do not see **Agent Sandboxes** in your project, see
    [Enable Agent Sandboxes](python.md#enable-agent-sandboxes).

Run Python in a remote [Agent Sandbox](index.md) from a Node.js application.
Your application is TypeScript or JavaScript. The code that your agent writes, and that the sandbox runs, is Python.

## Before you start

- [Enable Agent Sandboxes](python.md#enable-agent-sandboxes) for your project.
- [Get an execution key](python.md#get-an-execution-key) and set it as the `LOGFIRE_API_KEY` environment variable.
  The key also selects the data region, so you do not configure a URL.
- The examples use the `await using` syntax. TypeScript 5.2 or later supports it, and so does `tsx`. Plain JavaScript
  needs Node.js 24 or later. Without it, call `close()` in a `finally` block.

## Install the package

```bash
npm install @pydantic/logfire-agent-sandboxes @pydantic/monty
```

`@pydantic/monty` is the client for Pydantic Monty sandboxes. Version 1.5.0 or later is required.

## Run your first snippet

```ts title="index.mts"
import { agentSandboxes } from '@pydantic/logfire-agent-sandboxes'

await using pool = await agentSandboxes()
await using session = await pool.checkout()
console.log(await session.feedRun('sum([20, 21, 1])'))
```

Run `npx tsx index.mts`. It prints `42`.

`agentSandboxes()` returns a pool of sandboxes. The pool opens a connection when you call `pool.checkout()`, which
gives you a session with its own sandbox. Variables and functions defined in one `feedRun()` call are available in
later calls on the same session.

## Let sandbox code call your functions

Pass your own functions in `externalLookup`. Sandbox code calls them by name, and each call runs in your application.
Expose only the functions the code needs.

```ts title="index.mts"
import { agentSandboxes } from '@pydantic/logfire-agent-sandboxes'

const temperatures: Record<string, number> = { London: 14.0, Paris: 17.5, Tokyo: 21.0 }
const getTemperature = (city: string) => temperatures[city] // runs in your application

// written by your agent, runs in the sandbox
const agentCode = `
cities = ['London', 'Paris', 'Tokyo']
temperatures = {city: get_temperature(city) for city in cities}
max(cities, key=lambda city: temperatures[city])
`

await using pool = await agentSandboxes()
await using session = await pool.checkout()
console.log(await session.feedRun(agentCode, { externalLookup: { get_temperature: getTemperature } }))
```

This prints `Tokyo`. Host functions can also be `async`.

## Connect an agent

`@pydantic/logfire-ai-sdk-code-mode` connects the [Vercel AI SDK](https://ai-sdk.dev/) to Agent Sandboxes.
It turns your AI SDK tools into Python functions, and gives the model one `run_code` tool that calls them from a
script. See [Use with the Vercel AI SDK](https://github.com/pydantic/logfire-js/blob/main/docs/agent-sandboxes.md#use-with-the-vercel-ai-sdk)
in the Logfire JavaScript SDK docs.

The same page documents saved sessions, snapshots, pool options, and errors for TypeScript.

## Verify it worked

Run the [first snippet](#run-your-first-snippet), then open the [Live view](../guides/web-ui/live.md).
You should see a session span with a `run code` span inside it, showing the code, the result, and how long it took.

## Troubleshooting

- **``AgentSandboxError: Agent Sandboxes require a Logfire API key``**: no API key was found. Set `LOGFIRE_API_KEY`,
  or pass `apiKey` to `agentSandboxes()`.
- **`AgentSandboxRefusedError`**: the server rejected the API key. Use a project API key, not a personal key, with the
  `project:execute_agent_sandboxes` scope. Check that Agent Sandboxes are enabled for the project.
- **`SyntaxError` at `await using`**: your runtime does not support the syntax. Use TypeScript 5.2 or later, or
  Node.js 24 or later for plain JavaScript, or call `close()` in a `finally` block.

## Next steps

- [What sandbox code can do](limits.md): the parts of Python that scripts can use.
- [Answer questions that need dozens of tool calls](many-tool-calls.md): the scripts in the guides are Python, and
  run the same way from TypeScript.
- [Persist, resume, and fork sessions](sessions.md): how Logfire stores sessions, and for how long.
