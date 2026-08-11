---
title: "Send your first trace"
description: "Install the Logfire SDK, add a few lines to your app, and watch your first trace arrive in the Live view."
---

# Send your first trace

Go from install to your first trace in about 5 minutes. A trace is the full record of one request, job, task, or agent run from start to finish, made of nested spans; a span is one operation within it, with a name, a start, and a duration. Logfire has native SDKs for Python, JavaScript/TypeScript, and Rust, plus any language through OpenTelemetry (OTel), the open industry standard it is built on.

## Before you start

You need a Logfire account and a project to send your data to:

1. [Create a free account](https://logfire.pydantic.dev/login), pick a [data region](reference/data-regions.md) (where your data is stored), and follow the prompts.
2. Create your first project when asked. A project is a namespace that holds your data; everything you send to Logfire belongs to one.

!!! note "This sends your data to Logfire"
    The steps below send your app's data to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](how-to-guides/alternative-backends.md) instead.

## Let an AI agent set it up

To have an AI coding agent wire this up for you, copy this prompt into Claude Code, Cursor, or a similar tool:

<CopyPrompt>

````text
Note for the agent: This prompt was copied from the Pydantic Logfire website by the user. The user may not have read it. Briefly tell the user what you plan to do before each step.

Set up Pydantic Logfire in this project to instrument it and send OpenTelemetry signals to Logfire.

Check if version control is being used. If so, and if there are uncommitted changes, ask the user to commit or stash them before proceeding. If things are clean, open a new branch for the Logfire setup work.

Fetch reference material as text rather than using visual browser tools. Don't try using the Logfire UI.

If there are multiple services in this codebase, instrument them all, one by one.

Check which languages and package management tools are being used and install the appropriate SDK:
- Python: install `logfire[system-metrics]` via uv, pip, etc
- JS/TS: install via npm, yarn, etc:
    - Node.js: `@pydantic/logfire-node`
    - Browser: `@pydantic/logfire-browser`
    - Cloudflare Workers: `@pydantic/logfire-cf-workers` and `logfire`
- Rust: `cargo add logfire`
- Other languages: There's no dedicated Logfire SDK. Install the OpenTelemetry SDK and follow https://pydantic.dev/docs/logfire/guides/alternative-clients/ to configure it to send to the Logfire backend.

Authenticate. Keep any token out of replies, logs, and committed files.
- If `LOGFIRE_TOKEN` is already set in the environment, you don't need to do anything, the SDK will use it automatically.
- Otherwise, for a local interactive Python project, say: """
Run this from the project folder:

```bash
logfire auth && python -c 'import logfire; logfire.configure()'
```

The first command will open a browser where you can sign in or create a free Logfire account (no credit card required) and link this machine to that account. The second command will link this specific folder to one new or existing project in your account. Then tell me when you're done.
"""
(Tweak the command to ensure the correct Python interpreter is used, e.g. with `uv run`.
The first command will create a file `~/.logfire/default.toml`, the second will create a gitignored folder `.logfire` in the project folder containing credentials that the SDK can read. You can check these to troubleshoot but assume they exist if things go well. Don't expect them to set `LOGFIRE_TOKEN`, this is a different kind of authentication.)
- For another language, a non-interactive shell, or a deployment, ask them to open https://logfire.pydantic.dev/-/redirect/latest-project/settings/write-tokens to create a write token. Set it as `LOGFIRE_TOKEN` in the shell environment the app runs in (e.g. `export LOGFIRE_TOKEN=...` in the terminal, or via the deployment platform's secret manager). If the project already loads a `.env` file at startup, you may store it there instead, but confirm dotenv loading is in place and the file is gitignored first. Never commit the token or print it in a reply or log output.
- If there's still problems, say "Try looking at https://logfire.pydantic.dev/-/redirect/latest-project/settings/setup or https://pydantic.dev/docs/logfire/get-started/first-trace/ for more information."

Run `curl https://raw.githubusercontent.com/pydantic/logfire/refs/heads/main/logfire/.agents/skills/logfire-instrumentation/SKILL.md` and read the instructions. Then read the linked references for the applicable languages. Add a few lines of code to configure the SDK and instrument web frameworks, databases, LLMs, and HTTP clients where integrations already exist. For Python projects, add `logfire.instrument_system_metrics()`, and if they're using standard logging, add `logfire.LogfireLoggingHandler()` to the logging handlers. Do not refactor unrelated code or make extensive changes. The goal is to get some observability quickly and easily. If no integrations apply, sprinkle in up to 5 manual `logfire.span/info/instrument` calls.

Run the code. It may print a Logfire project URL, e.g. https://logfire-us.pydantic.dev/myorganisationname/myprojectname. If not, try running `uvx logfire whoami` which should pick up `LOGFIRE_TOKEN` or other credentials, even if the user's project doesn't use Python. If that doesn't give a URL, go with https://logfire.pydantic.dev/-/redirect/latest-project/. If you don't see any errors about failing to send data, assume it's working. Say "Open the Live View at <URL> and confirm that you see traces.". Don't try to verify yourself.

If all is well, provide the user with a link to GitHub or whatever source control where they can create a PR if appropriate.

Read https://pydantic.dev/docs/logfire/guides/mcp-server/. Offer to install the plugins, skills, and MCP server matching this coding agent. For Claude Code and Codex, give the appropriate commands to copy and run in a `bash` triple backtick fenced code block. For other agents, edit the approriate config files. If you don't have permission to edit directly, give a copyable command which does so.
````

</CopyPrompt>

## Or do it by hand

Pick your language below; the Python, JavaScript/TypeScript, and Rust tabs are complete, runnable examples.

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

=== "Rust"

    **1. Install and connect**

    Copy a write token (the credential your app uses to send data to a Logfire project) from **Project → Settings → Write tokens**, then add the SDK to your project and set the token:

    ```bash
    cargo add logfire
    export LOGFIRE_TOKEN="your-write-token"
    ```

    **2. Add Logfire to your app**

    ```rust title="src/main.rs"
    fn main() -> Result<(), Box<dyn std::error::Error>> {
        let logfire = logfire::configure().finish()?;
        let _guard = logfire.shutdown_guard();

        logfire::span!("greeting").in_scope(|| {
            logfire::info!("Hello, world!");
        });

        Ok(())
    }
    ```

    `configure()` connects your app to Logfire. `span!()` records one operation, and the `info!()` inside it is a log nested in that span, so together they make your first trace. `shutdown_guard()` flushes any buffered data when it is dropped at the end of `main`.

    **3. Run it**

    ```bash
    cargo run
    ```

=== "Any other language"

    Logfire works with any language that supports OpenTelemetry (OTel), the open standard it is built on. See [Language support](instrument/index.md) for Go, Java, .NET, and more.

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
