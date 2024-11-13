# HTTPX

The [`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] method can be used to instrument [HTTPX][httpx] with **Logfire**.

## Installation

Install `logfire` with the `httpx` extra:

{{ install_logfire(extras=['httpx']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

=== "Instrument the package"

    ```py title="main.py"
    import asyncio

    import httpx
    import logfire

    logfire.configure()
    logfire.instrument_httpx()

    url = "https://httpbin.org/get"

    with httpx.Client() as client:
        client.get(url)


    async def main():
        async with httpx.AsyncClient() as client:
            await client.get(url)


    asyncio.run(main())
    ```

=== "Instrument a single client"

    ```py title="main.py"
    import asyncio

    import httpx
    import logfire

    logfire.configure()

    url = 'https://httpbin.org/get'

    with httpx.Client() as client:
        logfire.instrument_httpx(client)
        client.get(url)


    async def main():
        async with httpx.AsyncClient() as client:
            logfire.instrument_httpx(client)
            await client.get(url)


    asyncio.run(main())

    ```

[`logfire.instrument_httpx()`][logfire.Logfire.instrument_httpx] uses the
**OpenTelemetry HTTPX Instrumentation** package,
which you can find more information about [here][opentelemetry-httpx].

[httpx]: https://www.python-httpx.org/
[opentelemetry-httpx]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html
