---
title: "AI Gateway"
description: "Route LLM calls through a single Logfire-managed endpoint with built-in spending limits, fallbacks, and usage tracking."
---

# AI Gateway

The Logfire AI Gateway lets you route LLM calls through a single endpoint with built-in spending limits, fallbacks, and usage tracking. Instead of scattering provider API keys across your applications, you point your existing SDKs (OpenAI, Anthropic, Google GenAI, Pydantic AI, or plain HTTP) at the gateway and authenticate with a gateway API key that you manage in Logfire.

The gateway gives you:

- **One endpoint, many providers** — call OpenAI, Anthropic, Google, AWS Bedrock, Groq, Mistral, and more through provider-compatible endpoints, using the SDKs you already have.
- **Key management** — project-scoped and personal API keys with per-key spending limits and expiry, managed in the Logfire UI.
- **Cost controls** — usage analytics plus daily, weekly, monthly, and total spending caps per key, and per-member limits.
- **Failover and load balancing** — routing groups let you group providers with priorities and weights.
- **Observability** — with telemetry enabled, every gateway request is traced into a Logfire project of your choice.

The gateway is configured per **organization** and is available on the Personal, Team, Growth, and Enterprise Cloud plans.

## Getting started

### Enable the gateway

1. Open Logfire and select your organization.
2. In the sidebar, under **AI Engineering**, click **Gateway**.
3. Click **Enable recommended setup**.

The recommended setup runs the whole onboarding in one go: it enables the gateway, activates built-in providers, turns on telemetry for a project, and creates your first API key (named **Quick Start**). When it finishes, click **Open Connect** to land on the Connect tab with a working snippet.

If you prefer to wire things up yourself, **Manual setup** just turns the gateway on and leaves providers, telemetry, and keys to you.

!!! note "Prerequisites"
    - You need to be an **organization admin** to enable the gateway and manage providers, routing, and spending. Non-admin members see the **Connect** and **API Keys** tabs only.
    - The organization needs at least one **project** — API keys and telemetry are scoped to a project.
    - On the Personal, Team, and Growth plans, built-in providers are billed against a prepaid balance and require a payment method; the exact fees and initial balance are shown during activation. You can skip this entirely by adding your own provider credentials instead (see [Providers](#providers)).

Once enabled, the Gateway page has these tabs: **Overview**, **Connect**, **API Keys**, **Providers**, **Routing**, **Spending**, and **Settings**.

### Connect an SDK

The **Connect** tab generates ready-to-run snippets: pick a provider, model, project, and API key, then copy the snippet for your SDK (curl, Pydantic AI, Python or TypeScript OpenAI SDK, Python Anthropic SDK, Google GenAI SDKs). You can also click **Try in playground** to test the same configuration in the Logfire Playground.

The gateway base URL depends on your Logfire region:

| Region | Gateway base URL |
|--------|------------------|
| US | `https://gateway-us.pydantic.dev/proxy` |
| EU | `https://gateway-eu.pydantic.dev/proxy` |
| Self-hosted | `https://<your-logfire-host>/proxy` |

Requests are addressed to `<gateway-base-url>/<route>`, where `<route>` is a provider slug (or routing group slug) from your **Providers** tab, and authenticated with an `Authorization: Bearer` header carrying your gateway API key.

For example, with an OpenAI-compatible provider whose slug is `openai`, in the US region:

=== "curl"

    ```bash
    curl https://gateway-us.pydantic.dev/proxy/openai/chat/completions \
      -H "Authorization: Bearer <YOUR_GATEWAY_API_KEY>" \
      -H "Content-Type: application/json" \
      -d '{
        "model": "gpt-5.2",
        "messages": [{"role": "user", "content": "Hello!"}]
      }'
    ```

=== "Python (OpenAI SDK)"

    ```python skip-run="true" skip-reason="external-connection"
    from openai import OpenAI

    client = OpenAI(
        api_key='<YOUR_GATEWAY_API_KEY>',
        base_url='https://gateway-us.pydantic.dev/proxy/openai',
    )

    response = client.chat.completions.create(
        model='gpt-5.2',
        messages=[{'role': 'user', 'content': 'Hello!'}],
    )
    print(response.choices[0].message.content)
    ```

=== "Pydantic AI"

    ```python skip-run="true" skip-reason="external-connection"
    import os

    from pydantic_ai import Agent

    os.environ['PYDANTIC_AI_GATEWAY_API_KEY'] = '<YOUR_GATEWAY_API_KEY>'
    os.environ['PYDANTIC_AI_GATEWAY_BASE_URL'] = 'https://gateway-us.pydantic.dev/proxy'

    agent = Agent('gateway/openai:gpt-5.2')
    print(agent.run_sync('Hello!').output)
    ```

Anthropic-type providers expose the Anthropic Messages API instead — the same pattern with the Anthropic SDK:

```python skip-run="true" skip-reason="external-connection"
from anthropic import Anthropic

client = Anthropic(
    api_key='<YOUR_GATEWAY_API_KEY>',
    base_url='https://gateway-us.pydantic.dev/proxy/anthropic',
)

response = client.messages.create(
    model='claude-opus-4-8',
    max_tokens=1024,
    messages=[{'role': 'user', 'content': 'Hello!'}],
)
print(response.content[0].text)
```

Use the Connect tab as the source of truth for your organization: it substitutes your actual provider slugs, a model the provider supports, your region's gateway URL, and (for keys created in your session) the plaintext API key.

## Concepts

### Providers

A provider is an upstream LLM service the gateway can forward requests to. Each provider has a **slug** which becomes the route segment in your request URL. There are two kinds:

- **Built-in providers** are managed by Logfire — no upstream account or API key needed. Usage is billed to your organization through a prepaid gateway balance (with configurable auto-recharge). Activation is a separate step from enabling the gateway and, on card-based plans, requires a payment method.
- **Bring-your-own-key (BYOK) providers** use credentials you supply on the **Providers** tab. Supported types include OpenAI, Anthropic, Google Vertex AI, Azure Foundry, AWS Bedrock, Groq, Hugging Face, Mistral, Ollama, Doubleword, and custom OpenAI-compatible endpoints. Upstream usage is billed directly by your provider.

### API keys

Gateway API keys authenticate requests to the gateway. Keys are scoped to a project and come in two flavors, both managed on the **API Keys** tab:

- **Project keys** are created and managed by admins, for shared or production use.
- **Personal keys** belong to an individual member (useful for local development); regular members can create and reveal their own.

Each key can have an expiry date and its own **spending limits** — daily, weekly, monthly, and total. The recommended setup creates a first project key named **Quick Start**.

### Routing groups

Routing groups (the **Routing** tab) let you define fallback strategies by grouping multiple providers under a single slug. Each member provider has a **priority** (failover order) and a **weight** (load balancing between members at the same priority level). Use the group's slug in place of a provider slug in your request URL to route through the group.

### Spending limits and balance

The **Spending** tab shows usage analytics for the organization, broken down by project, member, and API key. Cost controls exist at several levels:

- **Per-key limits** — daily, weekly, monthly, and total caps set on each API key.
- **Per-member limits** — daily, weekly, and monthly caps that admins can set for individual organization members.
- **Prepaid balance and auto-recharge** — built-in provider usage draws from a prepaid balance. You can enable auto-recharge with a threshold and a top-up target so the balance refills automatically before it runs out.

### Telemetry

The gateway can record every request as traces in a Logfire project, so you get full observability of your LLM traffic — models, latency, token usage, and conversation content — alongside the rest of your telemetry. The recommended setup turns this on for your chosen project; you can manage it later from the gateway **Settings** tab.

## Using the gateway with AI coding tools

The Logfire CLI can run a local authenticating proxy and launch supported AI coding tools against the gateway with short-lived credentials:

```bash
pip install "logfire[gateway]"
logfire gateway launch claude
```

Or run just the proxy and configure a tool manually with `logfire gateway serve`. See the [CLI reference](../../cli.md#ai-gateway-gateway) for details.

## See also

- [Gateway migration](../../../gateway-migration.md) — historical reference for users of the legacy standalone gateway.
- [Prompt Management: Access and Prerequisites](../prompt-management/plan-requirements.md) — prompt runs execute through the gateway and spend gateway budget.
- [Cost & Usage](../../../logfire-costs.md) — plan tiers and how usage is billed.
