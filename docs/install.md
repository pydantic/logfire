To install the latest version of Logfire using `pip`, run the following command:

```bash
pip install logfire --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
```

Or if you're using `poetry`:

```bash
poetry source add logfire-source https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
poetry add --source logfire-source logfire
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
logfire = {version = "*", source = "logfire-source"}
```

## Extra Dependencies

You can also install extra dependencies for Logfire.

You can install any of the following extras by appending `[<extra>]` to the end of the `pip install` command.

For example, to install with the extra dependencies for `fastapi` and `httpx`, you would do:

=== "PIP"

    ```bash
    pip install "logfire[fastapi,httpx]" --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    ```

    If you have a `requirements.txt`, you can add the extra dependencies to the `requirements.txt` file:

    ```txt title='requirements.txt'
    --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    logfire[fastapi,httpx]
    ```

=== "Poetry"

    ```bash
    poetry source add logfire-source https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    poetry add --source logfire-source "logfire[fastapi,httpx]"
    ```

    If you are using `poetry`, and have a `pyproject.toml`, you can add the
    extra dependencies to the `pyproject.toml` file:

    ```toml title='pyproject.toml'
    [tool.poetry.dependencies]
    python = "^3.8"
    logfire = {version = "*", source = "logfire-source", extras = ["fastapi", "httpx"]}
    ```

---

The available extras are:

- `all`: Install all extras.
- `dash`: The dashboard for Logfire.
    - Uses [`httpx`][httpx] to make requests to the Logfire API.
- `system-metrics`: To collect system metrics,
    - Uses [`opentelemetry-system-metrics`][opentelemetry-system-metrics] to collect system metrics.

[httpx]: https://www.python-httpx.org/
[pydantic]: https://pydantic-docs.helpmanual.io/
[opentelemetry-system-metrics]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/system_metrics/system_metrics.html
