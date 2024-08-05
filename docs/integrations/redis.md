# Redis

The [`logfire.instrument_redis()`][logfire.Logfire.instrument_redis] method will create a span for every command executed by your [Redis][redis] clients.

## Installation

Install `logfire` with the `redis` extra:

{{ install_logfire(extras=['redis']) }}

## Usage

Let's setup a container with Redis and run a Python script that connects to the Redis server to
demonstrate how to use **Logfire** with Redis.

### Setup a Redis Server Using Docker

First, we need to initialize a Redis server. This can be easily done using Docker with the following command:

```bash
docker run --name redis -p 6379:6379 -d redis:latest
```

### Run the Python script

```py title="main.py"
import logfire
import redis


logfire.configure()
logfire.instrument_redis()

client = redis.StrictRedis(host="localhost", port=6379)
client.set("my-key", "my-value")

async def main():
    client = redis.asyncio.Redis(host="localhost", port=6379)
    await client.get("my-key")

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

!!! info
    You can pass `capture_statement` to `logfire.instrument_redis()` to capture the Redis command.

    By default, it is set to `False` given that Redis commands can contain sensitive information.

The keyword arguments of `logfire.instrument_redis()` are passed to the `RedisInstrumentor().instrument()` method of the OpenTelemetry Redis Instrumentation package, read more about it [here][opentelemetry-redis].

[redis]: https://redis.readthedocs.io/en/stable/
[opentelemetry-redis]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html
