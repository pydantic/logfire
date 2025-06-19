---
integration: third-party
---

# Deno

Since v2.2, Deno has
[built-in support for OpenTelemetry](https://docs.deno.com/runtime/fundamentals/open_telemetry/).
The [logfire-js examples directory includes a `Hello World` example](https://github.com/pydantic/logfire-js/tree/main/examples/deno-project) that shows how to configure Deno
to export OpenTelemetry data to Logfire through environment variables.

You can also use the Logfire API package to create manual spans.
Install the `@pydantic/logfire-api` NPM package and call the appropriate methods
in your code.
