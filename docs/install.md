To install the latest version of Logfire, run the following command:

{{ install_logfire() }}

## Extra Dependencies

You can also install extra dependencies for Logfire.

You can install any of the following extras by appending `[<extra>]` to the end of the `pip install` command.

For example, to install with the extra dependencies for `fastapi` and `httpx`, you would do:

=== "PIP"

    ```bash
    pip install "logfire[fastapi,httpx]"
    ```

    If you have a `requirements.txt`, you can add the extra dependencies to the `requirements.txt` file:

    ```txt title='requirements.txt'
    logfire[fastapi,httpx]
    ```

=== "Poetry"

    ```bash
    poetry add "logfire[fastapi,httpx]"
    ```

    If you are using `poetry`, and have a `pyproject.toml`, you can add the
    extra dependencies to the `pyproject.toml` file:

    ```toml title='pyproject.toml'
    [tool.poetry.dependencies]
    python = "^3.8"
    logfire = {version = "*", extras = ["fastapi", "httpx"]}
    ```

---

The available extras are:

{{ extras_table }}

[httpx]: https://www.python-httpx.org/
[pydantic]: https://pydantic-docs.helpmanual.io/
[opentelemetry-system-metrics]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/system_metrics/system_metrics.html
