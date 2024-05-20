# Django

The [`logfire.instrument_django()`][logfire.Logfire.instrument_django] function can be used to instrument the [Django][django] web framework with **Logfire**.

See the documentation for the [OpenTelemetry Instrumentation Django][opentelemetry-django] package for more details.

## Installation

Install `logfire` with the `django` extra:

{{ install_logfire(extras=['django']) }}

## Usage

In the `settings.py` file, add the following lines:

```py
import logfire

# ...All the other settings...

# Add the following lines at the end of the file
logfire.configure()
logfire.instrument_django()
```

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use_cases/web_frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#capture-http-request-and-response-headers)

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[django-instrumentor]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#opentelemetry.instrumentation.django.DjangoInstrumentor
