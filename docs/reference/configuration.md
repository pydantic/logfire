---
title: "Logfire Configuration Guide & Environment Variables"
description: "Overview of configuring Pydantic Logfire: Programmatically, by using environment variables or by using a configuration file."
---
You can use the following ways to configure Logfire:

1. Programmatically via [`logfire.configure()`][logfire.configure]
2. Using [environment variables](#using-environment-variables)
3. Using a [configuration file](#using-a-configuration-file-pyprojecttoml) (`pyproject.toml`)

The order of precedence is as above.

## Programmatically via `configure`

For more details, please refer to our [API documentation][logfire.configure].

!!! note "Set up your project before running your application"

    `logfire.configure()` no longer creates or selects a project interactively.
    Existing project credentials and tokens continue to work. In a fresh checkout
    or credential directory, run `uvx logfire-cli wizard` for guided setup, or run
    `uvx logfire-cli auth` followed by `uvx logfire-cli init` from the project directory.
    Use `init --data-dir` if your application passes a custom `data_dir` to `configure()`.
    For a non-default [region](data-regions.md) or [self-hosted instance](self-hosted/overview.md),
    pass the same `--region` or `--base-url` to both `auth` and `init`.

    CLI sign-in alone does not configure the SDK. The CLI keeps your account login
    in the OS credential store; `init` saves the project's write token locally.
    For deployed applications, set `LOGFIRE_TOKEN` to a
    [write token](../how-to-guides/create-write-tokens.md) instead.
    `send_to_logfire=False` and `'if-token-present'` retain their existing behavior.

## Using environment variables

You can use the following environment variables to configure **Logfire**:

{{ env_var_table }}

Some parameters also accept an alternative environment variable, used only if the primary one above is not set:

| Primary variable | Alias |
|---|---|
| `LOGFIRE_SERVICE_NAME` | `OTEL_SERVICE_NAME` |
| `LOGFIRE_SERVICE_VERSION` | `OTEL_SERVICE_VERSION` |
| `LOGFIRE_TRACE_SAMPLE_RATE` | `OTEL_TRACES_SAMPLER_ARG` |
| `LOGFIRE_CONSOLE_SHOW_PROJECT_LINK` | `LOGFIRE_SHOW_SUMMARY` |

In addition, `LOGFIRE_CONFIG_DIR` sets the directory containing the [configuration file](#using-a-configuration-file-pyprojecttoml) (defaults to the current directory).

When using environment variables, you still need to call [`logfire.configure()`][logfire.configure],
but you can leave out the arguments.

## Using a configuration file (`pyproject.toml`)

You can use the `pyproject.toml` to configure **Logfire**.

Here's an example:

```toml
[tool.logfire]
project_name = "My Project"
console_colors = "never"
```

The keys are the same as the parameters of [`logfire.configure()`][logfire.configure].
