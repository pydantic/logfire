---
title: "Instrumenting print(): Logfire Print Logging Guide"
description: Transform every print() statement into a traceable log. This guide shows how to instrument print for structured logging with argument attribute extraction.
integration: logfire
---
# Instrumenting `print()`

[`logfire.instrument_print()`][logfire.Logfire.instrument_print] can be used to capture calls to `print()` and emit them
as **Logfire** logs. For example:

```py title="main.py"
import logfire

logfire.configure()
logfire.instrument_print()

name = 'World'
print('Hello', name)
```

This will still print as usual, but will also emit a log with the message `Hello World` as expected.

If Logfire is configured with [`inspect_arguments=True`][logfire.configure(inspect_arguments)],
the names of the arguments passed to `print` will be included in the log attributes
and will be used for scrubbing. In the example above, this means that the log will include
`{'name': 'World'}` in the attributes. The first argument `'Hello'` is automatically excluded because it's a literal.
If the variable name was `password`, then it would be scrubbed from both the message and the attributes.
