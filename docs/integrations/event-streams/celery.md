---
title: "Instrument Celery: trace every task your workers run"
description: "Create a span for every Celery task, including Celery beat, so you can follow background work end to end in Logfire."
integration: otel
---
# Celery

See every background task your [Celery][celery] workers run: the task name, how long it took, and
whether it failed, as a **span** (one unit of work with a name, a start, and a duration) in Logfire.
Spans link together into a **trace** (the full journey of one request), so a task shows up right next
to the request that enqueued it. Tasks scheduled with [Celery beat][celery-beat] are covered too.

## What you'll capture

- Each task run as a span, with its duration and status
- The task name and the arguments it ran with
- Failed tasks, with the error
- Tasks fired on a schedule by Celery beat

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `celery` extra:

{{ install_logfire(extras=['celery']) }}

## Usage

Call `logfire.configure()`, then [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery] to
record every task. Call both inside Celery's `worker_init` signal so they run once each worker process
starts.

!!! info
    The message broker you use doesn't matter for this integration: any
    [broker supported by Celery][broker supported by Celery] works.

The example below uses [Redis](https://redis.io/) as the broker. You can start one with Docker:

```bash
docker run --rm -d -p 127.0.0.1:6379:6379 redis
```

Then run the worker with `celery -A tasks worker --loglevel=info`:

```py title="tasks.py" hl_lines="9-10" skip-run="true" skip-reason="external-connection"
from celery import Celery
from celery.signals import worker_init

import logfire


@worker_init.connect()  # (1)!
def init_worker(*args, **kwargs):
    logfire.configure(service_name='worker')  # (2)!
    logfire.instrument_celery()


app = Celery('tasks', broker='redis://localhost:6379/0')  # (3)!


@app.task
def add(x: int, y: int):
    return x + y


add.delay(42, 50)  # (4)!
```

1. Celery emits [signals](https://docs.celeryq.dev/en/latest/userguide/signals.html) at points in the
   application lifecycle. `worker_init` fires once, as a worker process starts.
2. Set a `service_name` so you can tell this service's spans apart from the rest in Logfire.
3. Install `redis` with `pip install redis`.
4. Trigger the task. In your own app you'll more likely use `app.send_task("tasks.add", args=[42, 50])`,
   which hands the task to the broker and returns immediately.

## Verify it worked

Trigger a task, then open the [Live view](../../guides/web-ui/live.md). Within a few seconds you'll
see a span named after the task, with its duration and status: click it to see the arguments it ran
with.

<!-- TODO(app-verify): screenshot of a Celery task span in the Live view, showing the task name and duration -->

## Troubleshooting

Not seeing your tasks? Check that `logfire.configure()` ran before `instrument_celery()`, that your
write token is set (run `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN`
environment variable in production; see [Getting Started](../../index.md)), and that you called
`instrument_celery()` exactly once per worker process.

## Advanced

### Distributed tracing

To follow a task from the code that enqueued it all the way to the worker that ran it, call
`logfire.instrument_celery()` in **both** places:

1. The **worker processes** that execute tasks.
2. The **application that enqueues tasks** (for example, your Django or FastAPI web server).

This propagates the trace context (the small piece of tracking information passed alongside each
task) from the enqueuing app to the worker, so both ends appear in one trace. See the
[distributed tracing guide](../../how-to-guides/distributed-tracing.md#integrations) for details.

### Celery beat

If you schedule periodic tasks with **Celery beat**, instrument the beat process too, in its own
`beat_init` signal. Building on the example above:

```py title="tasks.py" hl_lines="13-16 20-26" skip-run="true" skip-reason="external-connection"
from celery import Celery
from celery.signals import beat_init, worker_init

import logfire


@worker_init.connect()
def init_worker(*args, **kwargs):
    logfire.configure(service_name='worker')
    logfire.instrument_celery()


@beat_init.connect()  # (1)!
def init_beat(*args, **kwargs):
    logfire.configure(service_name='beat')  # (2)!
    logfire.instrument_celery()


app = Celery('tasks', broker='redis://localhost:6379/0')
app.conf.beat_schedule = {  # (3)!
    'add-every-30-seconds': {
        'task': 'tasks.add',
        'schedule': 30.0,
        'args': (16, 16),
    },
}


@app.task
def add(x: int, y: int):
    return x + y
```

1. The `beat_init` signal fires once, as the beat process starts.
2. Use a different `service_name` so beat's spans are easy to tell apart.
3. Add a task to the beat schedule. See the
   [beat schedule docs](https://docs.celeryq.dev/en/latest/userguide/periodic-tasks.html#entries) for
   the full format.

This schedules `add` to run every 30 seconds with the arguments `16` and `16`. Run the beat process
with:

```bash
celery -A tasks beat --loglevel=info
```

### Passing options to the OpenTelemetry instrumentor

The keyword arguments of [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery] are passed
straight to the [`CeleryInstrumentor().instrument()`][opentelemetry.instrumentation.celery.CeleryInstrumentor]
method. See the [OpenTelemetry Celery instrumentation][opentelemetry-celery] docs for the full option
list.

## Reference

- API reference: [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery]
- Underlying OpenTelemetry package: [Celery instrumentation][opentelemetry-celery]

[celery]: https://docs.celeryq.dev/en/stable/
[celery-beat]: https://docs.celeryq.dev/en/latest/userguide/periodic-tasks.html
[opentelemetry-celery]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html
[broker supported by Celery]: https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/index.html
