---
title: "Instrument Celery: trace every task your workers run"
description: "Create a span for every Celery task, including Celery beat, so you can follow background work end to end in Logfire."
integration: otel
---
# Celery

See every background task your [Celery][celery] workers run: the task name, how long it took, and
whether it failed, as a **span** (one unit of work with a name, a start, and a duration) in Logfire.
Spans link together into a **trace** (the full journey of one request, made of nested spans).
[Enable tracing in the sender and the worker](#distributed-tracing) to see the task in the trace
that started it. You can also trace tasks that [Celery beat][celery-beat] starts on a schedule.

## What you'll capture

- Each task run as a span, with its duration and status
- The task name and the arguments it ran with
- Failed tasks, with the error
- Tasks fired on a schedule by Celery beat

!!! note "Task arguments are sent to Logfire"
    A task's arguments and any error details are recorded as span attributes and stored in Logfire, so they can include secrets or personal data. Use [scrubbing](../../how-to-guides/scrubbing.md) to redact sensitive values before they leave your machine.

{{ before_you_start() }}

## Installation

Install `logfire` with the `celery` extra:

{{ install_logfire(extras=['celery']) }}

The example uses Celery with Redis support. Install it in the same environment as Logfire.

```bash
pip install 'celery[redis]'
```

## Usage

### Start the worker

Call `logfire.configure()`, then [`logfire.instrument_celery()`][logfire.Logfire.instrument_celery] to
record every task. Call both inside Celery's `worker_process_init` signal so they run once in each
worker process, after the prefork pool forks it.

!!! info
    The message broker you use doesn't matter for this integration: any
    [broker supported by Celery][broker supported by Celery] works.

The example below uses [Redis](https://redis.io/) as the broker. You can start one with Docker:

```bash
docker run --rm -d -p 127.0.0.1:6379:6379 redis
```

Save the task and the worker setup in `tasks.py`.

```py title="tasks.py" hl_lines="9-10" skip-run="true" skip-reason="external-connection"
from celery import Celery
from celery.signals import worker_process_init

import logfire


@worker_process_init.connect(weak=False)  # (1)!
def init_worker(*args, **kwargs):
    logfire.configure(service_name='worker', distributed_tracing=True)  # (2)!
    logfire.instrument_celery()


app = Celery('tasks', broker='redis://localhost:6379/0')


@app.task
def add(x: int, y: int):
    return x + y
```

1. Celery emits [signals](https://docs.celeryq.dev/en/latest/userguide/signals.html) at points in the
   application lifecycle. `worker_process_init` fires once inside each worker process, after Celery
   forks it from the parent. Initializing in `worker_init` (which runs in the parent, before the fork)
   would build the exporter's background thread in the wrong process, so spans wouldn't export.
2. Set a service name so you can find the worker in Logfire. With `distributed_tracing=True`, the
   worker reads incoming trace context without a warning. Trace context is the information that
   connects the task to the trace that started it. Use this setting when you expect that information
   from senders you trust. See [incoming trace context](../../how-to-guides/distributed-tracing.md#unintentional-distributed-tracing).

Keep the worker running in its own terminal. Start it from the directory that contains `tasks.py`.

```bash
celery -A tasks worker --loglevel=info
```

### Distributed tracing

Enable Celery tracking in the sender process too. Here the sender is a script. In a web app, the
sender is the server that adds the task to the queue, such as FastAPI or Django. The integration in
the sender puts the trace context in the task message. The integration in the worker reads it.

Save `submit_task.py` beside `tasks.py`. The `Submit addition` span starts a trace before the script
sends the task. If your web app already records requests in Logfire, the task can join the request's
trace.

```py title="submit_task.py" hl_lines="5-6" skip-run="true" skip-reason="external-connection"
from tasks import add

import logfire

logfire.configure(service_name='sender')
logfire.instrument_celery()

with logfire.span('Submit addition'):
    add.delay(42, 50)
```

Open a second terminal in the same directory. Run the sender there.

```bash
python submit_task.py
```

## Verify it worked

The worker terminal shows that `tasks.add` succeeded with the result `92`. Open the
[Live view](../../guides/web-ui/live.md) and expand `Submit addition`. You should see these three
spans in one trace.

```text
Submit addition [sender]
└── apply_async/tasks.add [sender]
    └── run/tasks.add [worker]
```

Select `run/tasks.add` to see the task duration, status, and arguments.

## Troubleshooting

Not seeing your tasks? Check that `logfire.configure()` ran before `instrument_celery()`, that your
write token is set (install [uv](https://docs.astral.sh/uv/getting-started/installation/)
if needed, then run `uvx logfire-cli auth` if needed, then
`uvx logfire-cli init use` from your application's directory, or set the `LOGFIRE_TOKEN`
environment variable in production; see [Getting Started](../../index.md)), and that you called
`instrument_celery()` exactly once per worker process.

If `run/tasks.add` appears in a separate trace, check that the sender calls
`logfire.instrument_celery()` before it sends the task. Check the worker configuration too.
`distributed_tracing=False` makes the worker start a new trace for the task.

## Advanced

### Celery beat

If you schedule periodic tasks with **Celery beat**, instrument the beat process too, in its own
`beat_init` signal. Building on the example above:

```py title="tasks.py" hl_lines="13-16 20-26" skip-run="true" skip-reason="external-connection"
from celery import Celery
from celery.signals import beat_init, worker_process_init

import logfire


@worker_process_init.connect(weak=False)
def init_worker(*args, **kwargs):
    logfire.configure(service_name='worker')
    logfire.instrument_celery()


@beat_init.connect(weak=False)  # (1)!
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
