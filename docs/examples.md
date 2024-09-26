# Examples

!!! Tip "Logfire playground"
Example projects provide options to try out Logfire without needing to instrument your app in production.

These are working, stand-alone apps and projects that you can clone, spin up locally and play around with to get a feel for the different capabilities of Logfire.

**Got a suggestion?**

If you want to see an example of a particular language or library, [get in touch](help.md).

# Example repositories on GitHub

## JavaScript

### Cloudflare worker example

This example is based on the scaffolding created from `npm create cloudflare@latest`, and uses the [otel-cf-workers package](https://github.com/evanderkoogh/otel-cf-workers) to instrument a Cloudflare Worker and send traces and metrics to Logfire.

**Check it out on github:**
`https://github.com/pydantic/logfire/tree/main/examples/javascript/cloudflare-worker/`

### Express example

This example demonstrates how to use OpenTelemetry to instrument an Express application and send traces and metrics to Logfire.

**Check it out on github:**
`https://github.com/pydantic/logfire/tree/main/examples/javascript/express/`


## Python

### Auto-tracing example

This example is a simple Python financial calculator app which is instrumented with the [auto-tracing method](../../../docs/guides/onboarding-checklist/add-auto-tracing.md). If you spin up the server locally and interact with the calculator app, you'll be able to see traces come in automatically.

**Check it out on github:**
`https://github.com/pydantic/logfire/tree/main/examples/python/auto-tracing/`
