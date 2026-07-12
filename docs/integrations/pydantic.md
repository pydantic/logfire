---
title: "Instrument Pydantic: log and measure model validation"
description: "Get logs and metrics about your Pydantic model validation, including which models validate and how often validation fails."
integration: logfire
---
# Pydantic Validation

See every time your app validates a [Pydantic][pydantic] model (which model ran, whether it succeeded
or failed, and how often validation fails) in Logfire. Successful and failed validations become
**spans** (a span is one timed step, with a name and a duration) and are also counted as **metrics**
(a metric is a number tracked over time, like a validation count), so you get both individual records
and rolled-up totals.

Logfire ships a Pydantic plugin that hooks into Pydantic's validation. Unlike most integrations, you
don't call a `logfire.instrument_*` function on each object: you turn the plugin on once, through
configuration.

## What you'll capture

- Each model validation, marked as a success or a failure
- A count of validations and failures over time, as metrics
- The validation error for each failure

{{ before_you_start() }}

## Installation

Install `logfire`. The Pydantic plugin is included, with no separate extra:

{{ install_logfire() }}

## Usage

Enable the plugin in any one of these ways:

- Set the `LOGFIRE_PYDANTIC_PLUGIN_RECORD` environment variable to `all`.
- Set `pydantic_plugin_record` in `pyproject.toml`:

    ```toml
    [tool.logfire]
    pydantic_plugin_record = "all"
    ```

- Call [`logfire.instrument_pydantic()`][logfire.Logfire.instrument_pydantic]:

    ```py skip-run="true" skip-reason="global-instrumentation"
    import logfire

    logfire.instrument_pydantic()  # defaults to record='all'
    ```

If you use only the last option, note that only model classes defined and imported *after* the
`logfire.instrument_pydantic()` call are instrumented.

!!! note
    Remember to call [`logfire.configure()`][logfire.configure] at some point, before or after
    enabling the plugin and defining your models. Validations are only sent to Logfire once
    `logfire.configure()` has run.

## Verify it worked

Validate one of your models (for example, construct it from user input), then open the
[Live view](../guides/web-ui/live.md) for the individual validations, or the
[Metrics explorer](../guides/web-ui/metrics-explorer.md) for the validation counts. Within a few
seconds you'll see the validation appear.

## Troubleshooting

Not seeing your validations in Logfire? Check that `logfire.configure()` ran, that your write token is
set, that the plugin is enabled (via environment variable, `pyproject.toml`, or
`instrument_pydantic()`), and, if you used `instrument_pydantic()`, that your models are defined and
imported *after* that call.

## Advanced

### Third-party modules

By default the plugin does not instrument third-party modules, to avoid noise. Opt specific ones in
with the [`include`][logfire.PydanticPlugin.include] setting:

```py skip-run="true" skip-reason="global-instrumentation"
import logfire

logfire.instrument_pydantic(include={'openai'})
```

Opt your own modules out with the [`exclude`][logfire.PydanticPlugin.exclude] setting:

```py skip-run="true" skip-reason="global-instrumentation"
import logfire

logfire.instrument_pydantic(exclude={'app.api.v1'})
```

### Per-model configuration

For finer control, set options on an individual model with Pydantic's
[`plugin_settings`][pydantic.config.ConfigDict.plugin_settings] class parameter:

```py
from pydantic import BaseModel

from logfire.integrations.pydantic import PluginSettings


class Foo(BaseModel, plugin_settings=PluginSettings(logfire={'record': 'failure'})): ...
```

#### Record

The [`record`][logfire.integrations.pydantic.LogfireSettings.record] setting controls what is captured.
It takes one of:

- `all`: send spans and metrics for every validation. This is the default for
  `logfire.instrument_pydantic`.
- `failure`: send metrics for all validations, but spans only for failures.
- `metrics`: send only metrics.
- `off`: disable instrumentation for this model.

#### Tags

Tags add extra labels to the spans and metrics. Include them with the
[`tags`][logfire.integrations.pydantic.LogfireSettings.tags] key in
[`plugin_settings`][pydantic.config.ConfigDict.plugin_settings]:

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'all', 'tags': ('tag1', 'tag2')}}): ...
```

## Reference

- [`logfire.instrument_pydantic()`][logfire.Logfire.instrument_pydantic]: the Logfire API reference.
- [`record`][logfire.integrations.pydantic.LogfireSettings.record] and
  [`tags`][logfire.integrations.pydantic.LogfireSettings.tags]: per-model settings.
- [Pydantic validation docs][pydantic]: the library being instrumented.

[pydantic]: https://pydantic.dev/docs/validation/latest/get-started/
