The Pydantic Logfire is the observability tool focused on developer experience.

<!-- TODO(Marcelo): Add some images here. -->

## Features

<!-- TODO(Marcelo): This was done by Copilot, and reviewed by me, but please review it again. -->

- **Easy to use**: Logfire is easy to use, and configure.
- **Fast**: Logfire is fast, and doesn't add any overhead to your application.
- **Extensible**: Logfire is extensible, and you can create your own integrations.

## Installation

To install the latest version of Logfire, run the following command:

=== "pip"

    ```bash
    pip install logfire --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    ```

=== "poetry"

    ```bash
    poetry add logfire --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    ```

You can also add it to your project requirements:

<!-- TODO(Marcelo): Recommend people to pin the logfire version. -->
=== "pip"

    ```txt title='requirements.txt'
    --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
    logfire
    ```

=== "poetry"

    ```toml title='pyproject.toml'
    [tool.poetry.dependencies]
    logfire = { index = "https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/" }
    ```

## Usage

To use Logfire, it's simple as importing, and calling the desired function:

```py
import logfire

logfire.info("Hello, world!")
```

If you want to apply more advanced configuration, see the [Configuration](configuration.md) section.

### Automatic instrumentation

Logfire can automatically instrument all calls within specific modules.

```py
import logfire

logfire.install_automatic_instrumentation(modules=["app"])
```

### CLI

Logfire comes with a CLI that can help you with some tasks.

Run the following command to see what you can do with it:

```bash
logfire --help
```
