---
title: "Use the Logfire CLI"
description: "Set up a project, check Python instrumentation, and run an application with the current Logfire CLI."
---

# Use the Logfire CLI

The Logfire CLI connects your application to a project and helps you check its instrumentation. Install the `logfire` package to get the `logfire` command, or run the standalone CLI as `uvx logfire-cli`. The examples below use `logfire`; replace it with `uvx logfire-cli` if you have not installed the package. The `uvx` form requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

## Connect this directory to a project

Sign in and choose an existing project from your application's directory:

```bash
logfire auth
logfire init use
```

`init use` saves a write token in `.logfire/logfire_credentials.json`. The Python SDK reads that file when your application calls `logfire.configure()`. To create a project instead, use `logfire init new`. A token passed to `logfire.configure(token=...)` or set in `LOGFIRE_TOKEN` takes priority over the file. See [project configuration](configuration.md#programmatically-via-configure) for deployed applications and custom credential directories.

## Inspect (`inspect`)

Check which installed Python packages could use additional OpenTelemetry instrumentation (packages that add tracing to a library or framework):

```bash
logfire inspect
logfire inspect --ignore requests,httpx
```

The CLI selects your active Python environment, then a local `.venv`, then system Python. Use `--python .venv/bin/python` to choose one explicitly. That environment must have the Logfire SDK installed. `inspect` does not run your application or install packages. It exits with status 1 when it recommends packages, so read its report before treating that status as a failure. See the [standalone CLI inspect reference](https://github.com/pydantic/logfire-cli/blob/main/docs/commands/inspect.md) for options.

## Run (`run`)

Start a Python script, module, or installed Python command with automatic instrumentation:

```bash
logfire run app.py
logfire run -m uvicorn main:app
logfire run pytest tests/
```

`run` uses the selected Python environment's Logfire SDK. Pass `--no-summary` to hide the instrumentation report or `--exclude fastapi` to skip an integration. See the [standalone CLI run reference](https://github.com/pydantic/logfire-cli/blob/main/docs/commands/run.md) for interpreter selection and argument forwarding.

## Find other commands

- `logfire doctor python` prints Python, SDK, operating system, and related package versions.
- `logfire whoami` shows the account selected by the standalone CLI.
- `logfire project current` shows the project connected to this directory.
- `logfire token read` creates a read token for querying that project.

Run `logfire --help` for the installed command list. See the [standalone CLI command reference](https://github.com/pydantic/logfire-cli/blob/main/docs/README.md) for authentication, projects, tokens, queries, and coding-agent tools.
