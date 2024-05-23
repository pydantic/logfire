# Redis

The [`logfire.instrument_redis()`][logfire.Logfire.instrument_redis] method will create a span for every command executed by your [Redis][redis] clients.

## Installation

Install `logfire` with the `redis` extra:

{{ install_logfire(extras=['redis']) }}

## Usage

Let's see a minimal example below:

<!-- TODO(Marcelo): Create a secret gist with a docker-compose. -->

```py title="main.py"
import logfire
import redis


logfire.configure()
logfire.instrument_redis()

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

The keyword arguments of `logfire.instrument_redis()` are passed to the `RedisInstrumentor().instrument()` method of the OpenTelemetry Redis Instrumentation package, read more about it [here][opentelemetry-redis].

[redis]: https://redis.readthedocs.io/en/stable/
[opentelemetry-redis]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html
