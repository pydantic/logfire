# Celery

The [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery] method will create a span for every task
executed by your Celery workers.

## Installation

Install `logfire` with the `celery` extra:

{{ install_logfire(extras=['celery']) }}

## Usage

You'll need a message broker to run Celery. In this example, we'll run [RabbitMQ][rabbitmq-image] on a docker container.
You can run it as follows:

```bash
docker run -d --hostname my-rabbit \
    --name some-rabbit \
    # -e RABBITMQ_DEFAULT_USER=user \
    # -e RABBITMQ_DEFAULT_PASS=password \
    rabbitmq:3-management
```

Below we have a minimal example using Celery. You can run it with `celery -A tasks worker --loglevel=info`:

```py title="tasks.py"
import logfire
from celery import Celery
from celery.signals import worker_process_init


logfire.configure()

@worker_process_init.connect(weak=False)
def init_celery_tracing(*args, **kwargs):
    logfire.instrument_celery()

app = Celery("tasks", broker="pyamqp://localhost//")  # (1)!

@app.task
def add(x, y):
    return x + y

add.delay(42, 50)
```

1. Install `pyamqp` with `pip install pyamqp`.

The keyword arguments of [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery] are passed to the
[`CeleryInstrumentor().instrument()`][opentelemetry.instrumentation.celery.CeleryInstrumentor] method.

[celery]: https://docs.celeryq.dev/en/stable/
[opentelemetry-celery]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html
[rabbitmq-image]: https://hub.docker.com/_/rabbitmq
