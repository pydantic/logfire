# Auto-tracing

The [`logfire.install_auto_tracing`][logfire.Logfire.install_auto_tracing]
will trace all function calls in the specified modules.

This works by changing how those modules are imported,
so the function MUST be called before importing the modules you want to trace.

For example, suppose all your code lives in the `app` package, e.g. `app.main`, `app.server`, `app.db`, etc.
Instead of starting your application with `python app/main.py`,
you could create another file outside of the `app` package, e.g:

```py title="main.py"
import logfire

logfire.install_auto_tracing(modules=['app'])

from app.main import main

main()
```

## Filtering modules to trace

The `modules` argument can be a list of module names.
Any submodule within a given module will also be traced, e.g. `app.main` and `app.server`.
Other modules whose names start with the same prefix will not be traced, e.g. `apples`.

If one of the strings in the list isn't a valid module name, it will be treated as a regex,
so e.g. `modules=['app.*']` *will* trace `apples` in addition to `app.main` etc.

For even more control, the `modules` argument can be a function which returns `True` for modules that should be traced.
This function will be called with an [`AutoTraceModule`][logfire.AutoTraceModule] object, which has `name` and
`filename` attributes. For example, this should trace all modules that aren't part of the standard library or
third-party packages in a typical Python installation:

```py
import pathlib

import logfire

PYTHON_LIB_ROOT = str(pathlib.Path(pathlib.__file__).parent)


def should_trace(module: logfire.AutoTraceModule) -> bool:
    return not module.filename.startswith(PYTHON_LIB_ROOT)


logfire.install_auto_tracing(should_trace)
```

## Excluding functions from tracing

Once you've selected which modules to trace, you probably don't want to trace *every* function in those modules.
To exclude a function from auto-tracing, add the [`no_auto_trace`][logfire.no_auto_trace] decorator to it:

```py
from logfire import no_auto_trace

@no_auto_trace
def my_function():
    # Nested functions will also be excluded
    def inner_function():
        ...

    return other_function()


# This function is *not* excluded from auto-tracing.
# It will still be traced even when called from the excluded `my_function` above.
def other_function():
    ...


# All methods of a decorated class will also be excluded
@no_auto_trace
class MyClass:
    def my_method(self):
        ...
```

The decorator is detected at import time.
Only `@no_auto_trace` or `@logfire.no_auto_trace` are supported.
Renaming/aliasing either the function or module won't work.
Neither will calling this indirectly via another function.

This decorator simply returns the argument unchanged, so there is zero runtime overhead.
