---
title: "Get started with Logfire"
description: "Install the Logfire SDK, add a few lines to your app, and watch your first traces, logs, and metrics arrive in the Live view."
---

# Get started with Logfire

See what your app is actually doing: every request, database query, and error, with how long each one took, in your browser. This page takes you from install to your first data in Logfire in about five minutes.

Logfire is an observability platform (a place to see what your running software is doing) built on OpenTelemetry (OTel), the open industry standard for collecting traces, metrics, and logs. It has native SDKs for Python, JavaScript/TypeScript, and Rust, and works with any language through OpenTelemetry. General application observability and AI applications get the same treatment: the tools that show you a slow endpoint also show you a slow model call. [Read why Logfire exists](why.md).

## Before you start

You need a Logfire account and a project to send your data to:

1. [Create a free account](https://logfire.pydantic.dev/login), pick a [data region](reference/data-regions.md) (where your data is stored), and follow the prompts.
2. Create your first project when asked. A project is a namespace that holds your data; everything you send to Logfire belongs to one.

!!! note "This sends your data to Logfire"
    The steps below send your app's telemetry to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](how-to-guides/alternative-backends.md) instead.

## Send your first data

Pick your language. Each tab is a complete, runnable example.

=== "Python"

    **1. Install the SDK**

    {{ install_logfire() }}

    **2. Log in from your terminal**

    ```bash
    logfire auth
    ```

    This opens your browser to log in, then stores credentials in `~/.logfire/default.toml`.

    **3. Choose your project**

    From the root of your app, point the SDK at the project you created:

    ```bash
    logfire projects use <your-project>
    ```

    **4. Add Logfire to your app**

    ```py title="hello.py"
    import logfire

    logfire.configure()
    logfire.info('Hello, {name}!', name='world')
    ```

    `configure()` runs once to connect to Logfire; `info()` records a log (a timestamped record of a single event).

    **5. Run it**

    ```bash
    python hello.py
    ```

=== "JavaScript / TypeScript"

    **1. Install the SDK**

    ```bash
    npm install @pydantic/logfire-node
    ```

    **2. Connect to Logfire**

    Copy a write token (the credential your app uses to send data to a Logfire project) from **Project → Settings → Write tokens**, and set it in your environment:

    ```bash
    export LOGFIRE_TOKEN="your-write-token"
    ```

    For local development you can log in with the CLI instead: `npx logfire auth`, then `npx logfire projects use <your-project>`.

    **3. Add Logfire to your app**

    ```js title="hello.mjs"
    import * as logfire from '@pydantic/logfire-node'

    logfire.configure({ serviceName: 'hello-logfire' })

    await logfire.span('say hello', {
      callback: async () => {
        logfire.info('Hello world!')
      },
    })

    await logfire.shutdown()
    ```

    **4. Run it**

    ```bash
    node hello.mjs
    ```

    For browsers, Cloudflare Workers, and frameworks, see [Language support](languages.md).

=== "Any other language"

    Logfire works with any language that supports OpenTelemetry (OTel), the open standard it is built on. See [Language support](languages.md) for Go, Rust, Java, .NET, and more.

## See it in the Live view

Open the **Live view** in Logfire. Your log and any spans (a span is one unit of work: a single operation, with a name, a start, and a duration) appear as they arrive:

![Traces arriving in the Logfire Live view](images/logfire-live-view.png)

Each row is one operation, with its service, name, and duration. Click a row to open the full trace (the full journey of one request, made of nested spans) and read its attributes. The example above shows a checkout request with a nested validation error; your `hello world` shows up as a single row.

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
