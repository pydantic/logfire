# [Redis][redis]

The [OpenTelemetry Instrumentation Redis][opentelemetry-redis] package can be used to instrument Redis.

## Installation

Install `logfire` with the `redis` extra:

{{ install_logfire(extras=['redis']) }}

## Usage

Let's see a minimal example below:

<!-- TODO(Marcelo): Create a secret gist with a docker-compose. -->

```py title="main.py"
import logfire
import redis
from opentelemetry.instrumentation.redis import RedisInstrumentor


logfire.configure()
RedisInstrumentor().instrument()

# This will report a span with the default settings
client = redis.StrictRedis(host="localhost", port=6379)
client.get("my-key")

# This will report a span with the default settings
async def main():
    client = redis.asyncio.Redis(host="localhost", port=6379)
    await client.get("my-key")

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

You can read more about the Redis OpenTelemetry package [here][opentelemetry-redis].

[redis]: https://redis.readthedocs.io/en/stable/
[opentelemetry-redis]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html
