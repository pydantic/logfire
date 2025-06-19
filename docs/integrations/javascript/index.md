# JavaScript

Logfire offers first-class integration for the most popular JavaScript frameworks
and runtimes. Where appropriate (like Deno or Next.js), integration happens through the framework/runtime's built-in OTel mechanism.

In addition to the instrumentation itself, we ship an `@pydantic/logfire-api` package that mirrors the Python `logfire` package API for creating spans and reporting exceptions.

## Browser

The `@pydantic/logfire-browser` package wraps [the OpenTelemetry browser tracing](https://opentelemetry.io/docs/languages/js/getting-started/browser/) with some sensible defaults and provides a simple API for creating spans and reporting exceptions.

Refer to the [browser documentation section](./browser.md) for more details.

## Next.js

Next.js is a popular React framework for building server-rendered applications. It offers a first-party OTel integration through `@vercel/otel`, which is fully compatible with Logfire. In addition to that, the client-side can be instrumented with the `@pydantic/logfire-browser` package.

Refer to the [Next.js documentation section](./nextjs.md) for more details.

## Cloudflare

Instrumenting Cloudflare Workers is straightforward with Logfire. You can use the `@pydantic/logfire-cf-workers` package to instrument your worker handlers, and the `@pydantic/logfire-api` package to send logs and spans.

Refer to the [Cloudflare Workers documentation section](./cloudflare.md) for more details.

## Express

To instrument an Express app, use the `logfire` package, optionally using `dotenv` for reading environment variables from a file. Refer to the [Express documentation section](./express.md) for more details.

## Node.js

Generic Node.js scripts can be instrumented using the `logfire` package. Refer to the [Node.js documentation section](./node.md) for more details.

## Deno

Deno has built-in support for OpenTelemetry. You can configure OTel export to Logfire using environment variables. Refer to the [Deno documentation section](./deno.md) for more details.
