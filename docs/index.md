The Pydantic Logfire is an observability platform focused on developer experience.

Starting with Python, we're building a platform to let developers understand their software in a radically simpler and more enjoyable way.

## Why use Pydantic Logfire?

- Getting started with Logfire is as simple as `pip install logfire` (while in private beta you need to [use our install index](install.md)), `import logfire; logfire.info(...)`; Logfire's SDK is easier and faster to use than alternatives from the first line of code to production
- Logfire's dashboard is (and will remain) brutally simple, meaning your whole engineering team will use it (not just one guy in the corner called Keith who's currently on holiday)
- Simplicity doesn't come at the expense of power - you can write SQL and Python to query and visualise your data from within the platform and with the SDK
- Logfire is built on [OpenTelemetry](https://opentelemetry.io/), meaning you can use a wealth of existing tooling and infrastructure, including [instrumentation for many common Python packages](https://opentelemetry-python-contrib.readthedocs.io/en/latest/index.html)

![Screenshot](screenshot.png)

## Installation

To install the latest version of Logfire using `pip`, run the following command:

```bash
pip install logfire --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
```

For other installation methods, including using `poetry` or `requirements.txt`, see [Installation](install.md).

## Usage

To use Logfire, it's simple as importing, and calling the desired function:

```py
import logfire

logfire.info('Hello, {name}!', name='world') # (1)!

logfire.debug('Payment details: {amount=}, {state=}', amount=100, state='OK') # (2)!
```

1. This will log `Hello world!` with `info` level.
2. This will log `Payment details: amount=100, state=OK` with `debug` level.

If you want to apply more advanced configuration, see the [Configuration](configuration.md) section.

### Automatic instrumentation

Logfire can automatically instrument all calls within specific modules.

```py
import logfire

logfire.install_automatic_instrumentation(modules=['app'])
```

### CLI

Logfire comes with a CLI that can help you with some tasks.

Run the following command to see what you can do with it:

```bash
logfire --help
```
