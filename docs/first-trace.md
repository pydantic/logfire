---
title: "Send your first trace"
description: "Install the Logfire SDK, add a few lines to your app, and watch your first trace arrive in the Live view."
---

# Send your first trace

Go from install to your first trace in about 5 minutes. A trace is the journey of one request, made of nested spans; a span is one operation, with a name, a start, and a duration. Logfire has native SDKs for Python, JavaScript/TypeScript, and Rust, plus any language through OpenTelemetry (OTel), the open industry standard it is built on.

## Before you start

You need a Logfire account and a project to send your data to:

1. [Create a free account](https://logfire.pydantic.dev/login), pick a [data region](reference/data-regions.md) (where your data is stored), and follow the prompts.
2. Create your first project when asked. A project is a namespace that holds your data; everything you send to Logfire belongs to one.

!!! note "This sends your data to Logfire"
    The steps below send your app's data to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](how-to-guides/alternative-backends.md) instead.

## Let an AI agent set it up

To have an AI coding agent wire this up for you, copy this prompt into Claude Code, Cursor, or a similar tool:

<CopyPrompt>

```text
Set up Pydantic Logfire in this project. Read https://pydantic.dev/docs/logfire/get-started/first-trace/
and follow it to install the Logfire SDK, call logfire.configure() at the app's startup, and
instrument its web framework. Authenticate with a write token from the Logfire project's
Settings > Write tokens (set the LOGFIRE_TOKEN environment variable), not interactive
login. Then run the app and confirm a trace reaches the Logfire Live view.
```

</CopyPrompt>

## Or do it by hand

Pick your language below; the Python and JavaScript/TypeScript tabs are complete, runnable examples.

=== "Python"

    **1. Install and sign in**

    Run this in your project's terminal to install the SDK and sign in (`logfire auth` opens your browser to log in, no API key needed):

    ```bash
    uv add logfire
    uv run logfire auth
    ```

    Prefer pip? Use `pip install logfire`, then run `logfire auth` directly (without the `uv run` prefix). Prefer conda? Use `conda install -c conda-forge logfire`.

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
    uv run hello.py
    ```

    The first run asks you to pick or create a Logfire project, then sends your trace.

=== "JavaScript / TypeScript"

    **1. Install and connect**

    Copy a write token (the credential your app uses to send data to a Logfire project) from **Project → Settings → Write tokens**, then install the SDK and set the token:

    ```bash
    npm install @pydantic/logfire-node
    export LOGFIRE_TOKEN="your-write-token"
    ```

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

    For browsers, Cloudflare Workers, and frameworks, see [Language support](instrument/index.md).

=== "Any other language"

    Logfire works with any language that supports OpenTelemetry (OTel), the open standard it is built on. See [Language support](instrument/index.md) for Go, Rust, Java, .NET, and more.

## See it in the Live view

Open the [**Live view**](guides/web-ui/live.md) in Logfire. Your `greeting` trace appears as it arrives:

![Traces arriving in the Logfire Live view](images/logfire-live-view.png)

Each row is one span, with its service, name, and duration. Click a span to open its full trace and read its details. The example above shows a busier app: a checkout request with a nested validation error. Your `greeting` span shows up as a row, with the `Hello world!` log nested inside it.

## Get automatic traces

The `greeting` span is a manual example. Most of your traces should come automatically: add one line to instrument a framework or library you already use, and Logfire records every request, query, and outgoing call as a trace, without writing spans by hand.

```py skip="true" skip-reason="incomplete"
logfire.instrument_httpx()  # trace every outgoing HTTP request
```

Each integration ships as an extra, so install the matching one first: `pip install 'logfire[httpx]'` for the example above. See [Integrations](integrations/index.md) for FastAPI, Django, SQLAlchemy, HTTPX, and many more.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Nothing appears in the Live view | Not signed in, or no project or write token set | Run `logfire auth`, then run your app and pick a project when prompted; or set `LOGFIRE_TOKEN` from **Project → Settings → Write tokens** |
| The view looks empty | The time range does not include now | Widen the time range in the top right |
| A short script sends nothing | The program exited before its data was sent | Logfire sends data as your program runs and on exit; in JavaScript, call `await logfire.shutdown()` before exiting |

## Next steps

- **New to tracing?** [Core concepts](concepts.md) explains spans and traces and how to read them.
- **Want the full Python walkthrough?** The [Python onboarding guide](guides/onboarding-checklist/index.md) adds manual tracing, auto-tracing, and metrics, step by step.
- **Already using a framework?** [Integrations](integrations/index.md) add rich tracing to FastAPI, Django, SQLAlchemy, HTTPX, and many more with one line.
- **Building with AI?** [AI & LLM Observability](ai-observability.md) shows the requests, tool calls, tokens, and cost behind your model-powered features.
- **Not sure where to focus?** [Choose your path](get-started/choose-your-path.md) gives a short, ordered route for your role.
- **Ready to deploy?** Use a [write token](how-to-guides/create-write-tokens.md) in an environment variable instead of the CLI.
