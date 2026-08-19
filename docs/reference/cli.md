---
title: "Logfire SDK CLI: SDK Command Line Interface Guide"
description: "Use the Logfire CLI to simplify project management. Use commands to authenticate, logfire login, create new projects, and manage read/write tokens."
---
# SDK Command Line Interface

**Logfire** comes with a CLI used for authentication and project management:

```
{{ logfire_help }}
```

<iframe width="560" height="315" src="https://www.youtube.com/embed/di0ToWrOEPw" title="API Keys, CLI Auth & Trust Policies in Pydantic Logfire" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

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

### Log out (`auth logout`)

To log out and remove the locally stored credentials, run:

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

## Info (`info`)

To print the versions of `logfire`, your operating system, and related (OpenTelemetry) packages (useful when reporting a bug) run:

```bash
logfire info
```

## Who Am I (`whoami`)

To show the currently authenticated user and the URL of the current **Logfire** project, run:

```bash
logfire whoami
```

If you have one or more tokens configured (e.g. via the `LOGFIRE_TOKEN` environment variable), this shows the project each token belongs to instead.

## Projects

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

## Read tokens (`read-tokens`)

To create a [read token](../how-to-guides/query-api.md) for a project and print it to stdout, run:

```bash
logfire read-tokens --project <org>/<project> create
```

Because the token is printed to stdout, this composes well with other tools, e.g. configuring the [Logfire MCP server](../how-to-guides/mcp-server.md):

```bash
claude mcp add logfire -e LOGFIRE_READ_TOKEN=$(logfire read-tokens --project <org>/<project> create) -- uvx logfire-mcp@latest
```

## Run (`run`)

To run a Python script or module with **Logfire** instrumentation enabled automatically for all installed packages that have an available OpenTelemetry instrumentation, run:

```bash
logfire run script.py
# or run a module, forwarding any arguments after it:
logfire run -m my_module --my-arg
```

By default a summary box is printed to stderr showing which packages were instrumented; disable it with `--no-summary`. Use `--exclude` to skip instrumenting specific packages:

```bash
logfire run --exclude sqlalchemy,fastapi script.py
```

## Prompt (`prompt`)

To generate a prompt for an LLM to investigate an issue in your project (assuming the [Logfire MCP server](../how-to-guides/mcp-server.md) is configured), run:

```bash
logfire prompt "why are my requests slow?"
```

Use `--claude`, `--codex`, or `--opencode` to verify (and set up) the MCP configuration for the respective coding tool, `--update` to replace an existing Logfire MCP server configuration, and `--project <org>/<project>` to select the project.

[terms-of-service]: https://pydantic.dev/legal/terms-of-service
[privacy_policy]: https://pydantic.dev/legal/privacy-policy
