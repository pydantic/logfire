# Examples

These are working, stand-alone apps and projects that you can clone, spin up locally and play around with to get a feel for the different capabilities of Logfire.

**Got a suggestion?**

If you want to see an example of a particular language or library, [get in touch](help.md).

## Python

### Flask and SQLAlchemy example

This example is a simple Python financial calculator app using Flask and SQLAlchemy which is instrumented using the appropriate integrations as well as [auto-tracing](guides/onboarding-checklist/add-auto-tracing.md). If you spin up the server locally and interact with the calculator app, you'll be able to see traces come in automatically:

![Flask and SQLAlchemy example](/docs/images/logfire-screenshot-examples-flask-sqlalchemy.png)

[See it on GitHub :material-open-in-new:](https://github.com/pydantic/logfire/tree/main/examples/python/flask-sqlalchemy/){:target="_blank"}

## JavaScript

Currently we only have a Python SDK, but the Logfire backend and UI support data sent by any OpenTelemetry client. See the [alternative clients guide](guides/advanced/alternative-clients.md) for details on setting up OpenTelemetry in any language. We're working on a JavaScript SDK, but in the meantime here are some examples of using plain OpenTelemetry in JavaScript:

### Cloudflare worker example

This example is based on the scaffolding created from `npm create cloudflare@latest`, and uses the [otel-cf-workers package](https://github.com/evanderkoogh/otel-cf-workers) to instrument a Cloudflare Worker and send traces and metrics to Logfire.

[See it on GitHub :material-open-in-new:](https://github.com/pydantic/logfire/tree/main/examples/javascript/cloudflare-worker/){:target="_blank"}

### Express example

This example demonstrates how to use OpenTelemetry to instrument an Express application and send traces and metrics to Logfire.

[See it on GitHub :material-open-in-new:](https://github.com/pydantic/logfire/tree/main/examples/javascript/express/){:target="_blank"}
