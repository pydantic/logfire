---
title: "Logfire SDK CLI: SDK Command Line Interface Guide"
description: "Use the Logfire CLI to simplify project management. Use commands to authenticate, logfire login, create new projects, and manage read/write tokens."
---
# SDK Command Line Interface

**Logfire** comes with a CLI used for authentication and project management:

```
{{ logfire_help }}
```

## Authentication (`auth`)

You need to be authenticated to use the **Logfire**.

!!! abstract
    Read the [Terms of Service][terms-of-service] and [Privacy Policy][privacy_policy] if you want
    to know how we handle your data. :nerd_face:

To authenticate yourself, run the `auth` command in the terminal:

```bash
logfire auth
```

You will be prompted to select a [data region](./data-regions.md) (EU or US). To specify this
via the cli instead of interactively, use `logfire --region eu auth` or `logfire --region us auth`

!!! note
    If you're using a [self-hosted Logfire instance](./self-hosted/overview.md), you can authenticate by specifying your instance's URL using the `--base-url` flag:
    `logfire --base-url="https://<your_logfire_hostname>" auth`

Then you will be given the option to open logfire in your browser:
![Terminal screenshot with Logfire auth command](../images/cli/terminal-screenshot-auth-1.png)


After pressing `"Enter"`, you will be redirected to the browser to log in to your account.

![Browser screenshot with Logfire login page](../images/cli/browser-screenshot-auth.png)

Then, if you go back to the terminal, you'll see that you are authenticated! :tada:

![Terminal screenshot with successful authentication](../images/cli/terminal-screenshot-auth-2.png)

### Log Out (`auth logout`)

To log out and remove locally stored credentials, run:

```bash
logfire auth logout
```

## Clean (`clean`)

To clean _most_ the files created by **Logfire**, run the following command:

```bash
logfire clean
```

The clean command doesn't remove the logs, and the authentication information stored in the `~/.logfire` directory.

To also remove the logs, you can run the following command:

```bash
logfire clean --logs
```

## AI Gateway (`gateway`)

The gateway command runs a local OAuth proxy for the Logfire AI Gateway and can launch supported AI coding tools with short-lived credentials.

Install the optional dependencies before using it:

=== "uv"

    ```bash
    uv add "logfire[gateway]"
    ```

=== "pip"

    ```bash
    pip install "logfire[gateway]"
    ```

=== "poetry"

    ```bash
    poetry add "logfire[gateway]"
    ```

Launch a supported integration through the proxy:

```bash
logfire gateway launch claude
```

You can also run only the proxy and configure a tool manually:

```bash
logfire gateway serve
```

Use `--device-flow` if browser callback authorization is not available, or pass `--region eu` / `--region us` before `gateway` to select the Logfire region.

## Inspect (`inspect`)

The inspect command is used to identify the missing OpenTelemetry instrumentation packages in your project.

To inspect your project, run the following command:

```bash
logfire inspect
```

This will output the projects you need to install to have optimal OpenTelemetry instrumentation.

![Terminal screenshot with Logfire inspect command](../images/cli/terminal-screenshot-inspect.png)

## Who Am I (`whoami`)

!!! warning "🚧 Work in Progress 🚧"
    This section is yet to be written, [contact us](../help.md) if you have any questions.

## Projects

<!-- TODO(Marcelo): We can add the `logfire projects --help` here. -->

### List (`projects list`)

To check the projects you have access to, run the following command:

```bash
logfire projects list
```

You'll see something like this:

```bash
❯ logfire projects list
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Organization ┃ Project        ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ Kludex       │ backend        │
│ Kludex       │ worker         │
└──────────────┴────────────────┘
```

### Use (`projects use`)

To use an already created project, run the following command:

```bash
logfire projects use <project-name>
```

For example, to use the `backend` project, you can run:

```bash
logfire projects use backend
```

### Create (`projects new`)

To create a new project, run the following command:

```bash
logfire projects new <project-name>
```

Follow the instructions, and you'll have a new project created in no time! :partying_face:

## Read Tokens (`read-tokens`)

Read tokens allow programmatic read access to your project data via the [Query API](../how-to-guides/query-api.md).

### Create a Read Token (`read-tokens create`)

```bash
logfire read-tokens --project <organization>/<project> create
```

This outputs the token to stdout, making it convenient for use in scripts or CI environments.

## Run (`run`)

The `run` command executes a Python script or module with **automatic OpenTelemetry instrumentation**. It detects installed instrumentation packages and enables them without any code changes.

```bash
logfire run my_script.py
logfire run my_script.py arg1 arg2
logfire run -m my_module
```

Options:

- `-m MODULE` / `--module MODULE`: Run a module as a script (equivalent to `python -m MODULE`).
- `--exclude PACKAGE`: Exclude a package from auto-instrumentation (can be repeated).
- `--no-summary`: Suppress the instrumentation summary box printed at startup.

This is useful for quickly adding tracing to existing scripts without modifying their source code.

## Prompt (`prompt`)

The `prompt` command sets up the Logfire MCP server configuration for AI coding assistants and optionally retrieves a context prompt for a specific issue.

```bash
logfire prompt
logfire prompt --claude
logfire prompt --codex
logfire prompt --opencode
logfire prompt --update
logfire prompt <issue-id>
```

Options:

- `--claude`: Verify and configure the Claude Code MCP setup.
- `--codex`: Verify and configure the Codex MCP setup.
- `--opencode`: Verify and configure the OpenCode MCP setup.
- `--update`: Replace any existing Logfire MCP server configuration.
- `--project ORG/PROJECT`: Target a specific project (defaults to the current project).

## Info (`info`)

The `info` command displays version information for Logfire and related packages, useful for debugging and bug reports.

```bash
logfire info
```

[terms-of-service]: https://pydantic.dev/legal/terms-of-service
[privacy_policy]: https://pydantic.dev/legal/privacy-policy
