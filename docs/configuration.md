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

{{ env_var_table }}

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
