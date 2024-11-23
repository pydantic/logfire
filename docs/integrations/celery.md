# Celery

The [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery] method will create a span for every task
executed by your Celery workers.

The integration also supports the [Celery beat](https://docs.celeryq.dev/en/latest/userguide/periodic-tasks.html).

## Installation

Install `logfire` with the `celery` extra:

{{ install_logfire(extras=['celery']) }}

## Celery Worker

!!! info
    The broker you use doesn't matter for the Celery instrumentation.

    Any [broker supported by Celery] will work.

For our example, we'll use [redis](https://redis.io/). You can run it with Docker:

```bash
docker run --rm -d -p 6379:6379 redis
```

Below we have a minimal example using Celery. You can run it with `celery -A tasks worker --loglevel=info`:

```py title="tasks.py"
import logfire
from celery import Celery
from celery.signals import worker_init


@worker_init.connect()  # (1)!
def init_worker(*args, **kwargs):
    logfire.configure(service_name="worker")  # (2)!
    logfire.instrument_celery()

app = Celery("tasks", broker="redis://localhost:6379/0")  # (3)!

@app.task
def add(x: int, y: int):
    return x + y

add.delay(42, 50)  # (4)!
```

1. Celery implements different signals that you can use to run code at specific points in the application lifecycle.
   You can see more about the Celery signals [here](https://docs.celeryq.dev/en/latest/userguide/signals.html).
2. Use a `service_name` to identify the service that is sending the spans.
3. Install `redis` with `pip install redis`.
4. Trigger the task synchronously. On your application, you probably want to use `app.send_task("tasks.add", args=[42, 50])`.
   Which will send the task to the broker and return immediately.

## Celery Beat

As said before, it's also possible that you have periodic tasks scheduled with **Celery beat**.

Let's add the beat to the previous example:

```py title="tasks.py" hl_lines="11-14 17-23"
import logfire
from celery import Celery
from celery.signals import worker_init, beat_init


@worker_init.connect()
def init_worker(*args, **kwargs):
    logfire.configure(service_name="worker")
    logfire.instrument_celery()

@beat_init.connect()  # (1)!
def init_beat(*args, **kwargs):
    logfire.configure(service_name="beat")  # (2)!
    logfire.instrument_celery()

app = Celery("tasks", broker="redis://localhost:6379/0")
app.conf.beat_schedule = {  # (3)!
    "add-every-30-seconds": {
        "task": "tasks.add",
        "schedule": 30.0,
        "args": (16, 16),
    },
}

@app.task
def add(x: int, y: int):
    return x + y
```

1. The `beat_init` signal is emitted when the beat process starts.
2. Use a different `service_name` to identify the beat process.
3. Add a task to the beat schedule.
   See more about the beat schedule [here](https://docs.celeryq.dev/en/latest/userguide/periodic-tasks.html#entries).

The code above will schedule the `add` task to run every 30 seconds with the arguments `16` and `16`.

To run the beat, you can use the following command:

```bash
celery -A tasks beat --loglevel=info
```

The keyword arguments of [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery] are passed to the
[`CeleryInstrumentor().instrument()`][opentelemetry.instrumentation.celery.CeleryInstrumentor] method.

[celery]: https://docs.celeryq.dev/en/stable/
[opentelemetry-celery]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html
[rabbitmq-image]: https://hub.docker.com/_/rabbitmq
[broker supported by Celery]: https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/index.html
