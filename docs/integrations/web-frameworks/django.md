---
title: "Instrument Django: see every request your app handles"
description: "Add a few lines to your Django settings and see every request in Logfire: the view, the URL, timing, the database queries it ran, and any errors."
integration: otel
---
# Django

See every request your [Django][django] app handles (the view it hit, the URL, how long it took, the
database queries it ran, and any errors) as a **trace** (the full journey of one request, made of
nested **spans**, where each span is one unit of work with a name, a start, and a duration) in
Logfire.

## What you'll capture

- Each request as a span, with its HTTP status and duration
- The matched view and URL route
- The database queries run during the request (once you instrument your database engine, see below)
- Any errors raised while handling the request

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `django` extra:

{{ install_logfire(extras=['django']) }}

## Usage

Add two lines to your [Django settings file](https://docs.djangoproject.com/en/stable/topics/settings/):
`logfire.configure()` to connect to your project, and
[`logfire.instrument_django()`][logfire.Logfire.instrument_django] to record every request. The same
example also routes your standard-library log messages to Logfire.

```py hl_lines="14-15"
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

1. Django uses the standard library [logging](https://docs.python.org/3/library/logging.html) module, and can be configured using the
  [dictConfig format](https://docs.djangoproject.com/en/stable/topics/logging/#configuring-logging).
  As per our dedicated [logging section](../logging.md), you can use the
  [`LogfireLoggingHandler`][logfire.LogfireLoggingHandler] to send your log messages to Logfire.

!!! note
    The `logfire.configure()` and `logfire.instrument_django()` lines must be the last thing to
    execute in your settings. On a regular Django project, this means at the end of your settings
    file. If you use a setup with several settings files (for example, split into `local/prod/dev`),
    make sure you put those lines where they will be imported and executed last. Otherwise, the
    instrumentation might not work as expected.

## Verify it worked

Start your app (for example, `python manage.py runserver`) and open one of your pages in the browser.

Then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and go to the **Live**
view. Within a few seconds you should see a span for the request. Click it to see its duration, the
view that handled it, and the response status.

<!-- TODO(app-verify): screenshot of a Django request span in the Live view, showing the matched view and status -->

## Troubleshooting

Not seeing your requests in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_django()`.** Configure the connection
  first, then instrument.
- **You call `instrument_django()` exactly once**, at the very end of your settings file so nothing
  else runs after it.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually sent a request.** Spans appear only after a view is hit; reload a page.

## Advanced

### Instrumenting database queries

To see the database queries run during each request, instrument your database engine as well.

By default, Django [uses SQLite as the database engine]. To instrument it, call
[`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3]. If you use a different database,
find the matching instrumentation method in our [Integrations section].

### Running under Gunicorn

If you run your Django application with Gunicorn, you can also
[configure Logfire in Gunicorn](gunicorn.md).

## Reference

- API reference: [`logfire.instrument_django()`][logfire.Logfire.instrument_django]
- Underlying OpenTelemetry package: [Django instrumentation][opentelemetry-django]

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[uses SQLite as the database engine]: https://docs.djangoproject.com/en/stable/ref/databases/
[Integrations section]: ../index.md
