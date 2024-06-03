You can use the following ways to configure Logfire:

1. Programmatically via [`logfire.configure()`][logfire.configure]
2. Using environment variables
3. Using a configuration file (`pyproject.toml`)

The order of precedence is as above.

## Programmatically via `configure`

For more details, please refer to our [API documentation][logfire.configure].

## Using environment variables

You can use the following environment variables to configure **Logfire**:

{{ env_var_table }}

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
