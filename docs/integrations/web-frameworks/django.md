---
integration: otel
---

# Django

The [`logfire.instrument_django()`][logfire.Logfire.instrument_django] method can be used to instrument the [Django][django] web framework with **Logfire**.

## Installation

Install `logfire` with the `django` extra:

{{ install_logfire(extras=['django']) }}

!!! info
    If you use are using the **[Asynchronous support]** of Django, you'll also need to
    install the `asgi` extra:

    {{ install_logfire(extras=['django,asgi']) }}

## Usage

In the `settings.py` file, add the following lines:

```py
import logfire

# ...All the other settings...

# Add the following lines at the end of the file
logfire.configure()
logfire.instrument_django()
```

[`logfire.instrument_django()`][logfire.Logfire.instrument_django] uses the
**OpenTelemetry Django Instrumentation** package,
which you can find more information about [here][opentelemetry-django].

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[django-instrumentor]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#opentelemetry.instrumentation.django.DjangoInstrumentor
[Asynchronous support]: https://docs.djangoproject.com/en/dev/topics/async/#asynchronous-support
