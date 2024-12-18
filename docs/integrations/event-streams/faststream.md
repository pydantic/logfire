---
integration: built-in
---

# FastStream

To instrument [FastStream][faststream] with OpenTelemetry, you need to:

1. Call `logfire.configure()`.
2. Add the needed middleware according to your broker.

Let's see an example:

```python title="main.py"
from faststream import FastStream
from faststream.redis import RedisBroker
from faststream.redis.opentelemetry import RedisTelemetryMiddleware

import logfire

logfire.configure()

broker = RedisBroker(middlewares=(RedisTelemetryMiddleware(),))

app = FastStream(broker)


@broker.subscriber("test-channel")
@broker.publisher("another-channel")
async def handle():
    return "Hi!"


@broker.subscriber("another-channel")
async def handle_next(msg: str):
    assert msg == "Hi!"


@app.after_startup
async def test():
    await broker.publish("", channel="test-channel")
```

Since we are using Redis, we added the [`RedisTelemetryMiddleware`][faststream.redis.opentelemetry.RedisTelemetryMiddleware]
to the broker. In case you use a different broker, you need to add the corresponding middleware.

See more about FastStream OpenTelemetry integration in [their documentation][faststream-otel].

[faststream]: https://faststream.airt.ai/latest/
[faststream-otel]: https://faststream.airt.ai/latest/getting-started/opentelemetry/#faststream-tracing
