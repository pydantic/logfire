# [Django][django]

The [OpenTelemetry Instrumentation Django][opentelemetry-django] package can be used to instrument Django.

## Installation

Install `logfire` with the `django` extra:

{{ install_logfire(extras=['django']) }}

## Usage

<!-- TODO(Marcelo): Add a secret gist. -->

```py
from opentelemetry.instrumentation.django import DjangoInstrumentor

DjangoInstrumentor().instrument()
```

You can read more about the Django OpenTelemetry package [here][opentelemetry-django].

[django]: https://www.djangoproject.com/
[opentelemetry-django]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
