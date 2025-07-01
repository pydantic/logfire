---
integration: otel
---

# Django

The [`logfire.instrument_django()`][logfire.Logfire.instrument_django] method can be used to instrument the [Django][django] web framework with **Logfire**.

## Installation

Install `logfire` with the `django` extra:

{{ install_logfire(extras=['django']) }}

## Usage

In your [Django settings file](https://docs.djangoproject.com/en/stable/topics/settings/), add the following lines:

```py
import logfire

# ...All the other settings...

LOGGING = {  # (1)!
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'logfire': {
            'class': 'logfire.LogfireLoggingHandler',
        },
    },
    'root': {
        'handlers': ['logfire'],
    },
}

# Add the following lines at the end of the file
logfire.configure()
logfire.instrument_django()
```

1. Django uses the standard library [logging][] module, and can be configured using the
  [dictConfig format](https://docs.djangoproject.com/en/stable/topics/logging/#configuring-logging).
  As per our dedicated [logging section](../logging.md), you can make use of the
  [`LogfireLoggingHandler`][logfire.LogfireLoggingHandler] to redirect logs to Logfire.

[`logfire.instrument_django()`][logfire.Logfire.instrument_django] uses the
**OpenTelemetry Django Instrumentation** package,
which you can find more information about [here][opentelemetry-django].

!!! note
    The above lines must be the last thing to execute in your settings. On a regular Django project, this means
    at the end of your settings file. If you use an exotic configuration setup with several settings files (e.g. divided
    into `local/prod/dev`), make sure you put those lines where they will be imported and executed last. Otherwise, the
    instrumentation might not work as expected.

In case you are using Gunicorn to run your Django application, you can [configure Logfire in Gunicorn](gunicorn.md) as well.

## Instrumenting Django ORM Queries

To instrument Django ORM queries, you need to install the associated DB instrumentation tool, then add the corresponding instrumentation
command to your ‍settings file.

By default, the Django configuration [uses SQLite as the database engine].
To instrument it, you need to call [`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3].

If you are using a different database, check the available instrumentation methods in our [Integrations section].

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[uses SQLite as the database engine]: https://docs.djangoproject.com/en/stable/ref/databases/
[Integrations section]: ../index.md
