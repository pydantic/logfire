# Pydantic

Logfire has a [Pydantic plugin][pydantic-plugin] to instrument [Pydantic][pydantic] models.
The plugin provides logs and metrics about model validation.

To enable the plugin, do one of the following:

- Set the `LOGFIRE_PYDANTIC_PLUGIN_RECORD` environment variable to `all`.
- Set `pydantic_plugin_record` in `pyproject.toml`, e.g:

```toml
[tool.logfire]
pydantic_plugin_record = "all"
```

- Call [`logfire.instrument_pydantic`][logfire.Logfire.instrument_pydantic] with the desired configuration, e.g:

```py
import logfire

logfire.instrument_pydantic()  # Defaults to record='all'
```

Note that if you only use the last option then only model classes defined and imported *after* calling `logfire.instrument_pydantic`
will be instrumented.

!!! note
    Remember to call [`logfire.configure()`][logfire.configure] at some point, whether before or after
    calling `logfire.instrument_pydantic` and defining model classes.
    Model validations will only start being logged after calling `logfire.configure()`.

## Third party modules

By default, third party modules are not instrumented by the plugin to avoid noise. You can enable instrumentation for those
using the [`include`][logfire.PydanticPlugin.include] configuration.

```py
logfire.instrument_pydantic(include={'openai'})
```

You can also disable instrumentation for your own modules using the
[`exclude`][logfire.PydanticPlugin.exclude] configuration.

```py
logfire.instrument_pydantic(exclude={'app.api.v1'})
```

## Model configuration

If you want more granular control over the plugin, you can use the
[`plugin_settings`][pydantic.config.ConfigDict.plugin_settings] class parameter in your Pydantic models.

```py
from logfire.integrations.pydantic import PluginSettings
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings=PluginSettings(logfire={'record': 'failure'})):
    ...
```

### Record

The [`record`][logfire.integrations.pydantic.LogfireSettings.record] is used to configure what to record.
It can be one of the following values:

  * `all`: Send traces and metrics for all events. This is default value for `logfire.instrument_pydantic`.
  * `failure`: Send metrics for all validations and traces only for validation failures.
  * `metrics`: Send only metrics.
  * `off`: Disable instrumentation.

<!--
[Sampling](../usage/sampling.md) can be configured by `trace_sample_rate` key in
[`plugin_settings`][pydantic.config.ConfigDict.plugin_settings].

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'all', 'trace_sample_rate': 0.4}}):
    ...
```
-->

### Tags

Tags are used to add additional information to the traces, and metrics. They can be included by
adding the [`tags`][logfire.integrations.pydantic.LogfireSettings.tags] key in
[`plugin_settings`][pydantic.config.ConfigDict.plugin_settings].

```py
from pydantic import BaseModel


class Foo(
  BaseModel,
  plugin_settings={'logfire': {'record': 'all', 'tags': ('tag1', 'tag2')}}
):
```

[pydantic]: https://docs.pydantic.dev/latest/
[pydantic-plugin]: https://docs.pydantic.dev/latest/concepts/plugins/
