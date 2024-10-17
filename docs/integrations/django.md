# Django

The [`logfire.instrument_django()`][logfire.Logfire.instrument_django] method can be used to instrument the [Django][django] web framework with **Logfire**.

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

[`logfire.instrument_django()`][logfire.Logfire.instrument_django] uses the
**OpenTelemetry Django Instrumentation** package,
which you can find more information about [here][opentelemetry-django].

## Excluding URLs from instrumentation
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use-cases/web-frameworks.md#excluding-urls-from-instrumentation)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#exclude-lists)

## Capturing request and response headers
<!-- note that this section is duplicated for different frameworks but with slightly different links -->

- [Quick guide](use-cases/web-frameworks.md#capturing-http-server-request-and-response-headers)
- [OpenTelemetry Documentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#capture-http-request-and-response-headers)

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
[django-instrumentor]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html#opentelemetry.instrumentation.django.DjangoInstrumentor
