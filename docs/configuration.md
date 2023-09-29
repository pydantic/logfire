There are two ways to configure Logfire:

- [Programmatically via `configure`](#programmatically-via-configure)
- [Using environment variables](#using-environment-variables)

!!! note
    The programmatically _way_ has precedence over environment variables.

## Programmatically via `configure`

<!-- TODO(Marcelo): Need to add an explanation, and example on how to do this. -->

For more details, you can see our [API reference][logfire.configure].

## Using environment variables

You can use the following environment variables to configure LogFire:

<!-- TODO(Marcelo): We should generate this table from code. -->

| Name | Description |
| ---- | ----------- |
| LOGFIRE_API_ROOT | Used to set the base URL of the LogFire backend. |
| LOGFIRE_TOKEN | The token used to identify yourself. |
| LOGFIRE_SEND | Whether to send data to the LogFire backend. |
| LOGFIRE_PROJECT_NAME | The project name. |
| LOGFIRE_SERVICE_NAME | The service name. |

When using environment variables, you don't need to call [`logfire.configure()`][logfire.configure].
