---
title: "Getting started with Pydantic Logfire"
description: "Logfire is Pydantic's end-to-end AI engineering platform for seeing what your agents, services, applications, and hosts are doing. Pick a quickstart and send your first trace."
---

# Getting started with Pydantic Logfire

Logfire is Pydantic's end-to-end AI engineering platform. It shows you what your agents, services, applications, and hosts are actually doing: every LLM call, request, and query, and how long each one took. Built on OpenTelemetry (OTel), the open standard for traces, metrics, and logs, it spans your whole stack, from AI agents to the databases and servers behind them.

New here? [Create a free account](https://logfire.pydantic.dev/login), then pick a starting point below, or follow a [guided path for your role](get-started/choose-your-path.md).

## Quickstarts

<AgentSetup>

```text
Set up Pydantic Logfire in this project so it sends traces to Logfire. Follow the guide at https://pydantic.dev/docs/logfire/get-started/first-trace/.

1. Install the Logfire SDK for this project's language and initialize it at startup the way the guide describes for that language (for Python and JavaScript that is logfire.configure(); other languages may use OpenTelemetry), then instrument its web framework plus any LLM and HTTP clients. Don't refactor unrelated code.

2. Authenticate. If a `LOGFIRE_TOKEN` environment variable is already set, use it as-is. Otherwise, for a local Python project, install Logfire with the project's dependency manager (for example `uv add logfire`, `poetry add logfire`, or `pip install logfire`), then run `logfire auth` (or `uvx logfire auth`): this opens a browser where you sign in or create a free Logfire account (no credit card required) and a project, then links this machine, so nothing is hard-coded. For another language, a non-interactive shell, or a deployment, ask me for a write token (the credential that lets an app send data to Logfire) from Project > Settings > Write tokens and set it as the `LOGFIRE_TOKEN` environment variable; never commit it.

3. Run the app and confirm a trace reaches the Logfire Live view, then share the link.
```

</AgentSetup>

<div class="grid cards" markdown>

- <span class="lf-icon lf-icon--trace"></span> [__Send your first trace__](first-trace.md)

  Install the SDK and watch a trace arrive in the Live view, in about 5 minutes.

- <span class="lf-icon lf-icon--metrics"></span> [__Monitor your infrastructure__](guides/web-ui/hosts.md)

  Monitor hosts, Kubernetes, and cloud infrastructure alongside your application.

</div>

## Explore

<div class="grid cards" markdown>

- <span class="lf-icon lf-icon--agent"></span> [__Understand agent observability__](ai-observability.md)

  See how one trace connects an agent's model calls, tools, and the services behind them.

- <span class="lf-icon lf-icon--live"></span> [__Watch it live__](guides/web-ui/live.md)

  See traces and logs stream in, and drill into any span to read its full detail.

- <span class="lf-icon lf-icon--sql"></span> [__Query with SQL__](guides/web-ui/explore.md)

  Slice your data with the SQL you already know, not a proprietary query language.

- <span class="lf-icon lf-icon--dashboards"></span> [__Dashboards and alerts__](guides/web-ui/dashboards.md)

  Chart what matters and get notified in Slack when it changes.

- <span class="lf-icon lf-icon--evals"></span> [__Evaluate and ship AI features__](evaluate/overview.md)

  Run evaluations, manage prompts, and route models through the AI gateway.

- <span class="lf-icon lf-icon--metrics"></span> [__Metrics explorer__](guides/web-ui/metrics-explorer.md)

  Browse the metrics you're sending and break any of them down by dimension, no SQL required.

- <span class="lf-icon lf-icon--integrations"></span> [__Integrations__](integrations/index.md)

  FastAPI, Django, SQLAlchemy, HTTPX, and 40+ more, each with one line of setup.

</div>

## New to observability?

[Core concepts](concepts.md) explains spans, traces, and logs, and how to read them in Logfire. [Read why Logfire exists](why.md).
