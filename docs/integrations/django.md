# Django

The [OpenTelemetry Instrumentation Django][opentelemetry-django] package can be used to instrument [Django][django].

## Installation

Install `logfire` with the `django` extra:

{{ install_logfire(extras=['django']) }}

## Usage

You need to add the [`DjangoInstrumentor`][django-instrumentor] to your code before your application is started.

In the `settings.py` file, add the following lines:

```py
import logfire
from opentelemetry.instrumentation.django import DjangoInstrumentor

# ...All the other settings...

# Add the following lines at the end of the file
logfire.configure()
DjangoInstrumentor().instrument()
```

You can read more about the Django OpenTelemetry package [here][opentelemetry-django].

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use_cases/web_frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#capture-http-request-and-response-headers)

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[django-instrumentor]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#opentelemetry.instrumentation.django.DjangoInstrumentor
