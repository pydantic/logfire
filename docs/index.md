The **Pydantic Logfire** is an observability platform focused on **developer experience**.

Starting with Python, we're building a platform to let developers understand their software in a
radically simpler and more enjoyable way.

## Why use Pydantic Logfire?

### Easy to get started! :rocket:

It's as simple as `pip install logfire`, and run...

```bash
$ logfire auth
```

Then in your code:

```py
import logfire

logfire.info('Hello world!')
```

### OpenTelemetry under the hood :telescope:

Logfire is built on [OpenTelemetry](https://opentelemetry.io/), meaning you can
use a wealth of existing tooling and infrastructure, including
[instrumentation for many common Python packages](https://opentelemetry-python-contrib.readthedocs.io/en/latest/index.html).

### Simple, but powerful :muscle:

Logfire is built with simplicity in mind, but it doesn't come at the expense of power - you can
write SQL and Python to query and visualise your data from within the platform and with the SDK.

### The Dashboard is for everyone :busts_in_silhouette:

Logfire's dashboard is (and will remain) brutally simple, meaning your whole engineering team will
use it (not just one guy in the corner called Keith who's currently on holiday).

![Screenshot](screenshot.png)

## Installation

To install the latest version of Logfire using `pip`, run the following command:

```bash
pip install logfire
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

logfire.install_auto_tracing(modules=['app'])
```

You can read more about this on the [Auto Tracing](usage/auto_tracing.md) section.

### CLI

Logfire comes with a CLI that can help you with some tasks.

```bash
{{ logfire_help }}
```
