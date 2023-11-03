You can use the following ways to configure Logfire:

- [Programmatically via `configure`](#programmatically-via-configure)
- [Using environment variables](#using-environment-variables)
- [Using a configuration file (`pyproject.toml`)](#using-a-configuration-file-pyprojecttoml)

!!! note
    Settings passed programmatically have precedence over environment variables, and
    environment variables have precedence over the configuration file.

## Programmatically via `configure`

<!-- TODO(Marcelo): Need to add an explanation, and example on how to do this. -->

For more details, you can see our [API reference][logfire.configure].

## Using environment variables

You can use the following environment variables to configure Logfire:

<!-- TODO(Marcelo): We should generate this table from code. -->

| Name | Description |
| ---- | ----------- |
| LOGFIRE_BASE_URL | Used to set the base URL of the Logfire backend. |
| LOGFIRE_TOKEN | The token used to identify yourself. |
| LOGFIRE_SEND_TO_LOGFIRE | Whether to send data to the Logfire backend. |
| LOGFIRE_PROJECT_NAME | The project name. |
| LOGFIRE_SERVICE_NAME | The service name. |
| LOGFIRE_CONSOLE_ENABLED | Whether to enable terminal output. |
| LOGFIRE_CONSOLE_COLORS | Whether to control terminal output color. Possible values are `auto`, `always`, `never`. |
| LOGFIRE_CONSOLE_INDENT_SPAN | Whether to control span indent terminal output. |
| LOGFIRE_CONSOLE_INCLUDE_TIMESTAMP | Whether to show timestamp in terminal output. |
| LOGFIRE_CONSOLE_VERBOSE | Whether to print logs in verbose mode. |
| LOGFIRE_SHOW_SUMMARY | Whether to show a summary of the logs at the end of the program. |
| LOGFIRE_CREDENTIALS_DIR | The directory where to store the configuration file. |
| LOGFIRE_COLLECT_SYSTEM_METRICS | Whether to collect system metrics. |
| LOGFIRE_DISABLE_PYDANTIC_PLUGIN | Whether to disable the Pydantic plugin. |

When using environment variables, you don't need to call [`logfire.configure()`][logfire.configure].

## Using a configuration file (`pyproject.toml`)

You can use the `pyproject.toml` to configure Logfire.

Here's an example:

```toml
[tool.logfire]
project_name = "My Project"
console_colors = "never"
```

The keys are the same as the parameters of [`logfire.configure()`][logfire.configure].
