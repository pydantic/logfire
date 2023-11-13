You can use the following ways to configure Logfire:

1. Programmatically via [`logfire.configure()`][logfire.configure]
2. Using environment variables
3. Using a configuration file (`pyproject.toml`)

The order of precedence is as above.

## Programmatically via `configure`

For more details, please refer to our [API documentation][logfire.configure].

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

## Configuration details

### `exporter_fallback_to_local_file`

When Logfire fails to send a log to the server, it will write the log to a file to avoid data loss.
This parameter defines the path to the file where the logs will be written.
You can then load this file using `logfire backfill` (see [Backfilling data](advanced/backfill.md)).
If this file is locked by another process Logfire will add a random suffix to the file name.
