---
title: "Get started with Logfire"
description: "Install the Logfire SDK, add a few lines to your app, and watch your first logs and traces arrive in the Live view."
---

# Get started with Logfire

Logfire is an observability platform that shows you what your application is actually doing: every request, database query, LLM call, and error, with how long each one took, in your browser. It is built on OpenTelemetry (OTel), the open industry standard for collecting traces, metrics, and logs, and works across your whole stack, from traditional backends to AI agents.

This page takes you from install to your first trace in about 5 minutes. Logfire has native SDKs for Python, JavaScript/TypeScript, and Rust, plus any language through OpenTelemetry. A trace is the journey of one request, made of nested spans; a span is one operation, with a name, a start, and a duration. [Read why Logfire exists](why.md).

## Before you start

You need a Logfire account and a project to send your data to:

1. [Create a free account](https://logfire.pydantic.dev/login), pick a [data region](reference/data-regions.md) (where your data is stored), and follow the prompts.
2. Create your first project when asked. A project is a namespace that holds your data; everything you send to Logfire belongs to one.

!!! note "This sends your data to Logfire"
    The steps below send your app's data to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](how-to-guides/alternative-backends.md) instead.

## Send your first trace

Pick your language. Each tab is a complete, runnable example.

=== "Python"

    **1. Install and connect**

    Run this in your project's terminal to install the SDK, sign in (`logfire auth` opens your browser to log in, no API key needed), and connect this project:

    ```bash
    pip install logfire
    logfire auth
    logfire projects use <your-project>
    ```

    Prefer uv? Use `uv add logfire`, then prefix each `logfire` command with `uv run`. Prefer conda? Use `conda install -c conda-forge logfire`.

    **2. Add Logfire to your app**

    ```py title="hello.py"
    import logfire

    logfire.configure()

    with logfire.span('greeting'):
        logfire.info('Hello, {name}!', name='world')
    ```

    `configure()` connects your app to Logfire. `span()` records one operation, and `info()` writes a log (a timestamped record of a single event) inside it, so together they make your first trace.

    **3. Run it**

    ```bash
    python hello.py
    ```

=== "JavaScript / TypeScript"

    **1. Install and connect**

    Copy a write token (the credential your app uses to send data to a Logfire project) from **Project → Settings → Write tokens**, then install the SDK and set the token:

    ```bash
    npm install @pydantic/logfire-node
    export LOGFIRE_TOKEN="your-write-token"
    ```

    For local development you can log in with the CLI instead: `npx logfire auth`, then `npx logfire projects use <your-project>`.

    **2. Add Logfire to your app**

    ```js title="hello.mjs"
    import * as logfire from '@pydantic/logfire-node'

    logfire.configure({ serviceName: 'hello-logfire' })

    await logfire.span('greeting', {
      callback: async () => {
        logfire.info('Hello world!')
      },
    })

    await logfire.shutdown()
    ```

    `span()` records one operation, and the `info()` inside it is a log nested in that span, so together they make a trace. `shutdown()` sends anything still buffered before the script exits.

    **3. Run it**

    ```bash
    node hello.mjs
    ```

    For browsers, Cloudflare Workers, and frameworks, see [Language support](languages.md).

=== "Any other language"

    Logfire works with any language that supports OpenTelemetry (OTel), the open standard it is built on. See [Language support](languages.md) for Go, Rust, Java, .NET, and more.

## See it in the Live view

Open the [**Live view**](guides/web-ui/live.md) in Logfire. Your `greeting` trace appears as it arrives:

![Traces arriving in the Logfire Live view](images/logfire-live-view.png)

Each row is one span, with its service, name, and duration. Click a span to open its full trace and read its details. The example above shows a busier app: a checkout request with a nested validation error. Your `greeting` span shows up as a row, with the `Hello world!` log nested inside it.

## Get automatic traces

The `greeting` span is a manual example. Most of your traces should come automatically: add one line to instrument a framework or library you already use, and Logfire records every request, query, and outgoing call as a trace, without writing spans by hand.

```py
logfire.instrument_httpx()  # trace every outgoing HTTP request
```

See [Integrations](integrations/index.md) for FastAPI, Django, SQLAlchemy, HTTPX, and many more.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Nothing appears in the Live view | No project selected, or no write token set | Run `logfire projects use <your-project>`, or set `LOGFIRE_TOKEN` from **Project → Settings → Write tokens** |
| The view looks empty | The time range does not include now | Widen the time range in the top right |
| A short script sends nothing | The program exited before its data was sent | Logfire sends data as your program runs and on exit; in JavaScript, call `await logfire.shutdown()` before exiting |

## Next steps

- **New to tracing?** [Core concepts](concepts.md) explains spans and traces and how to read them.
- **Already using a framework?** [Integrations](integrations/index.md) add rich tracing to FastAPI, Django, SQLAlchemy, HTTPX, and many more with one line.
- **Building with AI?** [AI & LLM Observability](ai-observability.md) shows the calls, tool use, tokens, and cost behind your model-powered features.
- **Not sure where to focus?** [Choose your path](get-started/choose-your-path.md) gives a short, ordered route for your role.
- **Ready to deploy?** Use a [write token](how-to-guides/create-write-tokens.md) in an environment variable instead of the CLI.
