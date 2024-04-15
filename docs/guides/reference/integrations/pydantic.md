# Pydantic

Logfire has a [Pydantic plugin][pydantic-plugin] to instrument [Pydantic][pydantic] models.
The plugin provides logs and metrics about model validation.

You can enable it using the [`pydantic_plugin`][logfire.configure(pydantic_plugin)] configuration.

```py
import logfire

logfire.configure(pydantic_plugin=logfire.PydanticPlugin(record='all'))
```

## Third party modules

By default, third party modules are not instrumented by the plugin to avoid noise. You can enable instrumentation for those
using the [`include`][logfire.PydanticPlugin.include] configuration.

```py
import logfire

logfire.configure(pydantic_plugin=logfire.PydanticPlugin(record='all', include={'openai'}))
```

You can also disable instrumentation for your own modules using the
[`exclude`][logfire.PydanticPlugin.exclude] configuration.

```py
import logfire

logfire.configure(pydantic_plugin=logfire.PydanticPlugin(record='all', exclude={'app.api.v1'}))
```

## Model configuration

If you want more granular control over the plugin, you can use the the
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

  * `off`: Disable instrumentation. This is default value.
  * `all`: Send traces and metrics for all events.
  * `failure`: Send metrics for all validations and traces only for validation failures.
  * `metrics`: Send only metrics.

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
