# [Pydantic][pydantic]

<!-- TODO(Marcelo): Replace comments when mkdocstrings supports function parameter links. -->

Logfire has a [Pydantic plugin][pydantic-plugin] to instrument Pydantic models. The plugin provides logs and metrics
about model validation. The plugin is **disabled** by default. You can enable it using the
[`pydantic_plugin`][logfire.configure(pydantic_plugin)] configuration.

```py
from logfire import PydanticPluginOptions, configure

configure(pydantic_plugin=PydanticPluginOptions(record='all'))
```

By default, third party modules are not instrumented by the plugin to avoid noise. You can enable instrumentation for those
using the [`pydantic_plugin`][logfire.configure(pydantic_plugin)] configuration.

```py
from logfire import PydanticPluginOptions, configure

configure(pydantic_plugin=PydanticPluginOptions(record='all', include=('openai')))
```

You can also disable instrumentation for your own modules using the
[`pydantic_plugin`][logfire.configure(pydantic_plugin)] configuration.

```py
from logfire import PydanticPluginOptions, configure

configure(pydantic_plugin=PydanticPluginOptions(record='all', exclude=('app.api.v1')))
```

If you want more granular control over the plugin, you can use the the [`plugin_settings`][plugin_settings] class
parameter in your Pydantic models.

```py
from logfire.integrations.pydantic_plugin import PluginSettings
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings=PluginSettings(logfire={'record': 'failure'})):
    ...
```

The `record` config accepts following values:

  * `off`: Disable instrumentation. This is default value.
  * `all`: Send traces and metrics for all events.
  * `failure`: Send metrics for all validations and traces only for validation failures.
  * `metrics`: Send only metrics.


<!-- [Sampling](../usage/sampling.md) can be configured by `trace_sample_rate` key in [`plugin_settings`][plugin_settings].

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'all', 'trace_sample_rate': 0.4}}):
    ...
``` -->

Tags can be included by adding the `tags` key in [`plugin_settings`][plugin_settings].

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'all', 'tags': ('tag1', 'tag2')}}):
    ...
```

`tags` value can be one of the following options:

  * List of strings. e.g. `['tag1', 'tag2']`
  * Tuple of strings. e.g. `('tag1', 'tag2')`
  * Comma separated string. e.g. `'tag1,tag2'`

## Integration with other libraries

### OpenAI


[plugin_settings]: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.plugin_settings
[pydantic]: https://docs.pydantic.dev/latest/
[pydantic-plugin]: https://docs.pydantic.dev/latest/concepts/plugins/
