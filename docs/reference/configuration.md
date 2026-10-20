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

### Selecting instrumented function arguments

Use negative names in `extract_args` to omit individual parameters. For example,
`extract_args=['-self']` records the other arguments. When positive and negative
names are mixed, the positive names are selected first, then exclusions are applied.

To omit names across instrumented functions, use `instrument_exclude_args`:

```python
import logfire

logfire.configure(send_to_logfire=False, instrument_exclude_args=['self'])


class Worker:
    @logfire.instrument(extract_args=['-debug_payload'])
    def multiply(self, value: int, debug_payload: dict[str, str]) -> int:
        return value * 7


assert Worker().multiply(6, {'debug': 'caller context'}) == 42
```

This captures `value`, but not `self` or `debug_payload`. Global exclusions take
precedence over positive decorator selections and apply at call time, so functions
decorated before `configure()` also use them. Passing an empty sequence clears the
configuration. `configure(local=True, ...)` keeps the exclusions local to that instance.

These settings only control automatic argument extraction. They do not filter
explicitly logged attributes or recorded return values.


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
