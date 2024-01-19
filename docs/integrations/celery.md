# [Celery][celery]

The [OpenTelemetry Instrumentation Celery][opentelemetry-celery] package can be used to instrument Celery.

## Installation

Install `logfire` with the `celery` extra:

{{ install_logfire(extras=['celery']) }}

## Usage

```py
import logfire
from celery import Celery
from celery.signals import worker_process_init
from opentelemetry.instrumentation.celery import CeleryInstrumentor


logfire.configure()

@worker_process_init.connect(weak=False)
def init_celery_tracing(*args, **kwargs):
    CeleryInstrumentor().instrument()

app = Celery("tasks", broker="amqp://localhost")

@app.task
def add(x, y):
    return x + y

add.delay(42, 50)
```

You can read more about the Celery OpenTelemetry package [here][opentelemetry-celery].

[celery]: https://docs.celeryq.dev/en/stable/
[opentelemetry-celery]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html
