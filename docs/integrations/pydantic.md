# [Pydantic][pydantic]

Pydantic allows users to create [plugins](https://docs.pydantic.dev/latest/concepts/plugins/) that
can be used to extend the functionality of the library.

Logfire has a Pydantic plugin to instrument Pydantic models. The plugin provides logs and metrics
about model validation. The plugin is **disabled** by default. You can enable it using the
[`pydantic_plugin_record`](../configuration.md) configuration.

You can blacklist modules and modules by using [`pydantic_plugin_exclude`](../configuration.md), and whitelist
using [`pydantic_plugin_include`](../configuration.md).

You can also change Logfire Pydantic plugin configuration by using [`plugin_settings`][plugin_settings] config.

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'failure'}}):
    ...
```

The `record` config accepts following values:

  * `off`: Disable instrumentation. This is default value.
  * `all`: Send traces and metrics for all events.
  * `failure`: Send metrics for all validations and traces only for validation failures.
  * `metrics`: Send only metrics.


[Sampling](../advanced/sampling.md) can be configured by `trace_sample_rate` key in [`plugin_settings`][plugin_settings].

```py
from pydantic import BaseModel


class Foo(BaseModel, plugin_settings={'logfire': {'record': 'all', 'trace_sample_rate': 0.4}}):
    ...
```

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

### FastAPI

### OpenAI



[plugin_settings]: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.plugin_settings
[pydantic]: https://docs.pydantic.dev/latest/
