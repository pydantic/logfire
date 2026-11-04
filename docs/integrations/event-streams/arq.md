---
title: Trace ARQ jobs from enqueue to execution
description: Follow background jobs from the application that queues them to the ARQ worker that runs them.
integration: otel
---

# ARQ

Follow background jobs from the application that queues them to the [ARQ][arq] worker that runs
them. Logfire records a span (a timed operation) for the enqueue call and another for the job
execution. These spans include job names and IDs, and failed jobs include exception details. Job
arguments and return values are omitted from span attributes. Exception messages may still contain
application data.

{{ before_you_start() }}

## Install

{{ install_logfire(extras=['arq']) }}

The extra supports ARQ 0.26 and later, below 1.0, and installs the
[community OpenTelemetry instrumentor][instrumentor]. Its dependencies currently require Redis
Python client versions below 6 and wrapt versions below 2.

## Queue and run a job

Start a local Redis server for ARQ to store jobs:

```bash
docker run --rm -p 127.0.0.1:6379:6379 redis:7
```

Save this as `arq_demo.py` and run `python arq_demo.py`. The script queues a job and runs a worker
until the queue is empty.

```py title="arq_demo.py" hl_lines="8-9" skip-run="true" skip-reason="external-connection"
import asyncio

from arq.connections import create_pool
from arq.worker import Worker

import logfire

logfire.configure(distributed_tracing=True)
logfire.instrument_arq()


async def greet(ctx, name):
    return f"Hello, {name}!"


async def main():
    queue = "arq:queue:logfire-demo"
    redis = await create_pool()
    try:
        job = await redis.enqueue_job("greet", "World", _queue_name=queue)
        assert job is not None
        worker = Worker([greet], redis_pool=redis, queue_name=queue, burst=True, handle_signals=False)
        await worker.async_run()
        print(await job.result(timeout=5))
    finally:
        await redis.aclose(close_connection_pool=True)


if __name__ == "__main__":
    asyncio.run(main())
```

In an application with separate producer and worker processes, call
[`logfire.instrument_arq()`][logfire.Logfire.instrument_arq] once in each process, after
`logfire.configure(distributed_tracing=True)` and before queueing or running jobs. Distributed
tracing lets the worker continue the trace started by the producer. Instrumentation applies to
all ARQ activity in the process. A repeated call leaves the first installation in effect.

When rolling out instrumentation, update every worker that reads a queue before instrumenting
its producers. Instrumented producers add trace context as a reserved `_carrier` job keyword.
An uninstrumented worker can pass it through to the job function and cause the job to fail.

## Verify

The script prints `Hello, World!`. In the [Live view](../../guides/web-ui/live.md), look for two
`greet` spans in one trace. The enqueue span carries the queue name. The nested worker span carries
the same job ID.

## Troubleshooting

- **Redis connection refused.** Check that Redis is running and port 6379 is available.
- **Enqueue raises `IndexError`.** With instrumentor version 0.50b1, pass the job name as the
  first positional argument, as in the example.
- **A job fails with an unexpected `_carrier` keyword.** With instrumentor version 0.50b1,
  leave `OTEL_PYTHON_ARQ_EXCLUDED_TASKS` unset when producers and workers are instrumented.
- **The spans appear in separate traces.** Check that both processes are instrumented and that
  the worker accepts distributed trace context.

[arq]: https://arq-docs.helpmanual.io/
[instrumentor]: https://pypi.org/project/opentelemetry-instrumentation-arq/
