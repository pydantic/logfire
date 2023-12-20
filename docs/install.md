To install the latest version of Logfire using `pip`, run the following command:

```bash
pip install logfire --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
```

Or if you're using `poetry`:

```bash
poetry source add logfire-source https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
poetry add logfire
```

You can also add it to your project requirements:

```txt title='requirements.txt'
--extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
logfire
```

Or add to `pyproject.toml` if you're using `poetry`:

```toml title='pyproject.toml'
[[tool.poetry.source]]
name = "logfire-source"
url = "https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/"

[tool.poetry.dependencies]
python = "^3.8"
pydantic = "^2.0"
python-dotenv = "^1.0.0"
requests = "^2.31.0"
pytest = "^7.4.2"
logfire = {version = "*", source = "logfire-source"}
```

## Extra Dependencies

You can also install extra dependencies for Logfire. Below is a table of the extras and their dependencies.

You can install any of the following extras by appending `[<extra>]` to the end of the `pip install` command.

```bash
pip install "logfire[<extra>]" --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
```

<!-- Create table -->
| Name | Packages | Description |
| ---- | -------- | ----------- |
| all  | [`httpx`][httpx], [`opentelemetry-system-metrics`][opentelemetry-system-metrics] | Install `dash` and `system-metrics` extras. |
| dash | [`httpx`][httpx] | The dashboard for Logfire. |
| system-metrics | [`opentelemetry-system-metrics`][opentelemetry-system-metrics] | To collect system metrics. |

[httpx]: https://www.python-httpx.org/
[pydantic]: https://pydantic-docs.helpmanual.io/
[opentelemetry-system-metrics]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/system_metrics/system_metrics.html
