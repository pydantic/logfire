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

### Get the project URL after configuring

After [`logfire.configure()`][logfire.configure] has run, `logfire.project_url` returns the URL of the project that telemetry is sent to:

```python
import logfire

logfire.configure(token='...')

project_url = logfire.project_url
```

`project_url` is a string such as `https://logfire-us.pydantic.dev/my-organization/my-project`, or `None` when the URL isn't known, for example when `send_to_logfire=False` or on AWS Lambda, where Logfire skips the background token check. The value comes from the credentials file, or from validating the configured token. Reading `logfire.project_url` waits for any background token validation to finish, so the value is stable.

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
