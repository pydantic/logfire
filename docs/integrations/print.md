---
title: "Capture print() calls as structured logs"
description: "Turn print() calls into Logfire logs, with arguments captured as structured attributes you can search and filter."
integration: logfire
---
# Instrumenting `print()`

Turn your existing `print()` calls into Logfire **logs** (individual timestamped records of something
that happened), so the output you already print shows up in Logfire (searchable and filterable)
next to the **traces** (the full journey of one request through your app) from the rest of your code.
Your `print()` calls still print to the console as usual.

## What you'll capture

- Each `print()` call as a log message
- Its timestamp
- The printed arguments, captured as structured attributes you can search and filter

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Copy it from **Project → Settings → Write tokens** in the Logfire web app. New to Logfire?
Start with [Getting Started](../index.md).

## Installation

Install `logfire`:

{{ install_logfire() }}

No extra library needed: this works with Python's built-in `print()`.

## Usage

Call `logfire.configure()` to connect to your project, then
[`logfire.instrument_print()`][logfire.Logfire.instrument_print] to capture every `print()` call and
emit it as a Logfire log.

```py title="main.py"
import logfire

logfire.configure()
logfire.instrument_print()

name = 'World'
print('Hello', name)
```

This will still print as usual, but will also emit a log with the message `Hello World` as expected.

## Verify it worked

Run your program, then open the [Live view](../guides/web-ui/live.md) in the Logfire web app.
Within a few seconds you'll see your printed message as a record.

<!-- TODO(app-verify): screenshot of the log record in the Live view -->

## Advanced

### Capturing argument names as attributes

If Logfire is configured with [`inspect_arguments=True`][logfire.configure(inspect_arguments)],
the names of the arguments passed to `print` will be included in the log attributes
and will be used for scrubbing. In the example above, this means that the log will include
`{'name': 'World'}` in the attributes. The first argument `'Hello'` is automatically excluded because
it's a literal. If the variable name was `password`, then it would be scrubbed from both the message
and the attributes.

## Troubleshooting

Not seeing your printed output in Logfire? Check that `logfire.configure()` ran first, your write
token is set, and `logfire.instrument_print()` was called.

## Reference

- API reference: [`logfire.instrument_print()`][logfire.Logfire.instrument_print]
