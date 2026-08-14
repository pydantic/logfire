---
title: "Instrument Dramatiq: trace queued work from send to completion"
description: "Connect Dramatiq producers and workers in one distributed trace, including delayed tasks and retries."
integration: custom
---
# Dramatiq

See when your application sends a [Dramatiq][dramatiq] message, how long it waits, and what happens
when a worker processes it. Logfire records each send and task as a **span** (one unit of work: a
single operation, with a name, a start, and a duration). The spans form a **trace** (the full journey
of one request, made of nested spans), so you can follow queued work from creation to completion.

The integration adds trace context and **baggage** (small key/value data that rides along with a
request across services) to the message options. It does not record message arguments or results.

{{ before_you_start() }}

## Install the integration

Install Logfire with the `dramatiq` extra in every producer and worker environment:

{{ install_logfire(extras=['dramatiq']) }}

## Trace messages through your broker

Configure Logfire, create your broker, and call
[`logfire.instrument_dramatiq()`][logfire.Logfire.instrument_dramatiq] before declaring or sending
actors. The example uses Redis, so it also needs `pip install redis` and a Redis server on
`localhost:6379`.

```python title="tasks.py" hl_lines="6 8" skip-run="true" skip-reason="external-connection"
import dramatiq
from dramatiq.brokers.redis import RedisBroker

import logfire

logfire.configure(distributed_tracing=True)
broker = RedisBroker(host='localhost')
logfire.instrument_dramatiq(broker)
dramatiq.set_broker(broker)


@dramatiq.actor
def send_email(address: str) -> None:
    print(f'Email sent to {address}')


if __name__ == '__main__':
    send_email.send('hello@example.com')
```

`distributed_tracing=True` is intentional: the worker accepts trace context from messages so it can
continue the producer's trace. Only accept messages from brokers you trust. If you set
`distributed_tracing=False`, producer and worker spans start separate traces instead. See
[unintentional distributed tracing](../../how-to-guides/distributed-tracing.md#unintentional-distributed-tracing)
for the tradeoffs.

Call `instrument_dramatiq()` in both applications if producers and workers run in separate
processes. If you omit `broker`, Logfire instruments the broker returned by
`dramatiq.get_broker()`. Calling it again for the same broker returns the installed middleware and
does not add duplicate spans.

The integration covers actor sends, direct broker enqueues, callbacks, pipelines, retries, delayed
messages, and other paths that call `broker.enqueue()`. Each enqueue gets a producer span. A retry
keeps its original creation context while each queue delivery gets a new producer span. The next
worker span uses the latest delivery as its parent and links back to the original creation context.

The returned middleware also provides `uninstrument()`. Call it to finish active worker spans,
remove the middleware, and restore the broker's original `enqueue()` method.

## Verify the trace

Run `dramatiq tasks`, then run `python tasks.py`. Open the
[Live view](../../guides/web-ui/live.md) and find `send_email send`. Its trace should contain a
`send_email process` span with the queue name and message ID. Failed tasks include the exception on
the worker span, and retries appear as later producer spans.

## Troubleshoot missing spans

- **You see sends but no task processing:** call `logfire.configure()` and
  `logfire.instrument_dramatiq()` inside the worker process too.
- **You see task processing but no send:** instrument the broker in the producer before sending
  messages.
- **You use a custom broker:** pass that broker instance to `instrument_dramatiq(broker)` instead of
  relying on Dramatiq's global broker.
- **A process exits while handling a task:** use Dramatiq's graceful worker shutdown so the
  middleware can finish active spans.

## Next steps

Read the [distributed tracing guide](../../how-to-guides/distributed-tracing.md) to learn how Logfire
connects work across services. You can also add [custom baggage](../../reference/advanced/baggage.md)
to correlate queued work with application metadata.

[dramatiq]: https://dramatiq.io/
