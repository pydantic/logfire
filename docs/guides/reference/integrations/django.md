# Django

The [OpenTelemetry Instrumentation Django][opentelemetry-django] package can be used to instrument [Django][django].

## Installation

Install `logfire` with the `django` extra:

{{ install_logfire(extras=['django']) }}

## Usage

You need to add the [`DjangoInstrumentor`][django-instrumentor] to your code before your application is started.

In the `manage.py` please add the following lines:

```py hl_lines="6-7 14-15"
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

import logfire
from opentelemetry.instrumentation.django import DjangoInstrumentor


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

    logfire.configure()
    DjangoInstrumentor().instrument()

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

You can read more about the Django OpenTelemetry package [here][opentelemetry-django].

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](../../use_cases/web_frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#capture-http-request-and-response-headers)

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[django-instrumentor]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#opentelemetry.instrumentation.django.DjangoInstrumentor
