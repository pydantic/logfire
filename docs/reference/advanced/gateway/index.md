---
title: "AI Gateway"
description: "Route LLM calls through a single Logfire-managed endpoint with built-in spending limits, fallbacks, and usage tracking."
---

# AI Gateway

The Logfire AI Gateway lets you route LLM calls through a single endpoint with built-in spending limits, fallbacks, and usage tracking. Instead of scattering provider API keys across your applications, you point your existing SDKs (OpenAI, Anthropic, Google GenAI, Pydantic AI, or plain HTTP) at the gateway and authenticate with a gateway API key that you manage in Logfire.

!!! note
    The gateway is for **routing** your model calls. If you only want to **see and debug** the calls you already make, you don't need it: [instrument a framework](../../../integrations/llms/index.md) instead.

The gateway gives you:

- **One endpoint, many providers**: call OpenAI, Anthropic, Google, AWS Bedrock, Groq, Mistral, and more through provider-compatible endpoints, using the SDKs you already have.
- **Key management**: project-scoped and personal API keys with per-key spending limits and expiry, managed in the Logfire UI.
- **Cost controls**: included per-key limits and an organization-wide budget, plus project and member limits.
- **Failover and load balancing**: gateway endpoints route requests across one or more providers, using priorities and weights.
- **Observability**: with telemetry enabled, every gateway request is traced into a Logfire project of your choice.

The gateway is configured per **organization** and is available on the Personal, Team, Growth, and Enterprise Cloud plans, and on self-hosted Logfire.

## Getting started

For the shortest path to a working call, follow [Send your first Gateway request](first-request.md). It covers the provider choice, credential, Connect snippet, and a check that the request arrived. Then add only the controls you need:

- [Add your own provider](byok-providers.md) to use an existing upstream account.
- [Route across providers](endpoints.md) for traffic sharing or failover behind one URL.
- [Protect request data](protect-data.md) with prebuilt or custom Guardrails.
- [Optimize requests](optimizations.md) with endpoint-scoped instructions.
- [Control spending](spending-policies.md) with included key and organization limits, or advanced spending policies.

### Plan availability

You do not need a paid plan to send Gateway requests or set basic spending limits. Some configuration options require a higher plan or Early Access:

| Feature | Availability |
|---------|--------------|
| Connect, endpoint priorities and weights, and key, organization, project, and member spending limits | All Gateway plans, including Personal. |
| BYOK providers | Up to 3 on Personal and Team; unlimited on Growth, Enterprise, and self-hosted Logfire. |
| Custom provider base URLs and custom OpenAI- or Anthropic-compatible providers | Team, Growth, Enterprise, or self-hosted Logfire. |
| Prebuilt and custom-pattern Guardrails; Optimizations | Via Early Access on Growth, Enterprise, or self-hosted Logfire. |
| Spending policies | Experimental, enabled through the same Early Access settings. Not required for the included spending limits. |
| Presidio protections | Enterprise Cloud or self-hosted Logfire, with Guardrails enabled. |

[**Settings → Early access**](https://logfire.pydantic.dev/settings/early-access) is available when your account belongs to an eligible organization. Its feature choices apply to your account in this browser, not automatically to every member. Individual guides explain which option to enable. For pricing and Enterprise contract details, see [Logfire plans](https://pydantic.dev/pricing).

### Enable the gateway

1. Open [**AI Engineering → Gateway**](https://logfire.pydantic.dev/-/redirect/default-org/-/gateway) and check the selected organization.
2. Click **Enable recommended setup**.

The recommended setup enables the gateway, checks built-in providers, turns on telemetry for a project, installs recommended guardrails, and creates your first API key (named **Quick Start**). If built-in providers require a payment method, setup can finish without activating them; add a payment method or [bring your own provider](byok-providers.md) before sending a request. When a route is ready, open **Connect** for a working snippet.

If you prefer to wire things up yourself, **Manual setup** just turns the gateway on and leaves providers, telemetry, and keys to you.

!!! note "Prerequisites"
    - You need to be an **organization admin** to enable the gateway and manage providers, gateway endpoints, and spending. Non-admin members see the **Connect** and **API Keys** tabs only.
    - The organization needs at least one **project**: API keys and telemetry are scoped to a project.
    - Built-in providers draw from a prepaid balance. Activation may require a payment method and set up auto-recharge; an eligible promotional credit can provide balance-backed access without a saved payment method. Review the amounts and terms shown during activation. You can instead add your own provider credentials (see [Providers](#providers)). On the Personal plan, your own credentials must be for a supported vendor at its permitted endpoint; custom endpoints require a paid plan.

Once enabled, the Gateway page has tabs for **Overview**, **Connect**, **API Keys**, **Providers**, **Endpoints**, **Spending**, and **Settings**. Other controls, including **Guardrails** and **Optimizations**, appear when available to your organization.

Gateway links open your default organization in the hosted app. Switch organizations if needed before changing settings. On self-hosted Logfire, use the same navigation in your own deployment.

### Connect an SDK

The [**Connect** tab](https://logfire.pydantic.dev/-/redirect/default-org/-/gateway/connect) generates ready-to-run snippets: choose a route, get or select a project API key, then copy the snippet for your SDK (curl, Pydantic AI, Python or TypeScript OpenAI SDK, Python Anthropic SDK, Google GenAI SDKs). You can change the model under **Customize connection** or click **Try in playground** to test the same configuration in the Logfire Playground. See the [step-by-step Connect guide](first-request.md) for payment, credential, verification, and troubleshooting paths.

The gateway base URL depends on your Logfire region:

| Region | Gateway base URL |
|--------|------------------|
| US | `https://gateway-us.pydantic.dev/proxy` |
| EU | `https://gateway-eu.pydantic.dev/proxy` |
| Self-hosted | `https://<your-logfire-host>/proxy` |

Requests are addressed to `<gateway-base-url>/<route>`, where `<route>` is a provider slug from the **Providers** tab or a gateway endpoint slug from the **Endpoints** tab. Authenticate the request with an `Authorization: Bearer` header carrying your gateway API key.

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

Anthropic-type providers expose the Anthropic Messages API instead: the same pattern with the Anthropic SDK:

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

- **Built-in providers** are managed by Logfire: no upstream account or API key needed. Usage draws from your organization's prepaid gateway balance. Activation is separate from enabling Gateway; it may require a payment method, while eligible promotional credit can allow activation without one. Auto-recharge is configurable when a payment method is on file.
- **Bring-your-own-key (BYOK) providers** use credentials you supply on the **Providers** tab. The current provider picker includes OpenAI, Anthropic, Google AI Studio, Google Vertex AI, Azure Foundry, AWS Bedrock, Groq, Hugging Face, Mistral, Ollama, Doubleword, Modal, TypeSafe AI, and custom OpenAI- or Anthropic-compatible endpoints. Upstream usage is billed directly by your provider.

!!! note "Custom endpoints require a paid plan or self-hosted Logfire"
    On the Team, Growth, and Enterprise plans, and on self-hosted Logfire, you can point a BYOK provider at any HTTPS endpoint, including your own OpenAI- or Anthropic-compatible server.

    On the Personal plan, each BYOK provider must use its vendor's endpoint. Vendors with a single public API, such as OpenAI, Anthropic, or Groq, use that API's standard base URL. Vendors with per-account endpoints, such as Azure Foundry, Google Vertex AI, and AWS Bedrock, accept only that vendor's own endpoint hosts. Custom OpenAI- and Anthropic-compatible providers are not available.

### API keys

Gateway API keys authenticate requests to the gateway. Keys are scoped to a project and come in two flavors, both managed on the **API Keys** tab:

- **Project keys** are created and managed by admins, for shared or production use.
- **Personal keys** belong to an individual member (useful for local development); regular members can create and reveal their own.

Each key can have an expiry date and its own **spending limits**: daily, weekly, monthly, and total. The recommended setup creates a first project key named **Quick Start**.

### Gateway endpoints

A gateway endpoint routes requests across one or more providers under a single slug. Manage gateway endpoints on the **Endpoints** tab. Higher-priority provider groups are tried first; weights share traffic within a group. Use the endpoint's slug in place of a provider slug in your request URL. See [Route across providers](endpoints.md) for the setup steps.

### Spending limits and balance

The **Spending** tab shows usage analytics for the organization, broken down by project, member, and API key. Every Gateway plan includes these limits:

- **Per-key limits**: daily, weekly, monthly, and total caps set on each API key.
- **Organization-wide limits**: a shared daily, weekly, or monthly budget across the organization, set in **Gateway → Settings**.
- **Per-project limits**: daily, weekly, and monthly caps for a selected project, also in **Gateway → Settings**.
- **Per-member limits**: daily, weekly, and monthly caps that admins can set for individual organization members.

**Spending policies** add reusable provider- and model-scoped budgets attached to an organization, project, member, or API key. They are experimental and available through Growth and Enterprise Early Access, or on self-hosted Logfire. They are not required to limit spending. See [Control Gateway spending](spending-policies.md) for both included limits and advanced policy setup.

Separately, built-in provider usage draws from a **prepaid balance**. You can enable auto-recharge with a threshold and a top-up target. Auto-recharge adds funds; it does not increase your configured spending limits.

### Telemetry

The gateway can record every request as traces in a Logfire project, so you get full observability of your LLM traffic (models, latency, token usage, and conversation content) alongside the rest of your telemetry. The recommended setup turns this on for your chosen project; you can manage it later from the gateway **Settings** tab.

## Using the gateway with AI coding tools

The Logfire CLI can run a local authenticating proxy and launch supported AI coding tools against the gateway with short-lived credentials:

```bash
pip install "logfire[gateway]"
logfire gateway launch claude
```

!!! note
    For self-hosted Logfire, set `LOGFIRE_BASE_URL` to your Logfire URL or pass `--base-url "https://<your-logfire-host>"` before `gateway`. If the Gateway is exposed at a different URL, set `LOGFIRE_GATEWAY_URL` or append `--gateway-url "https://<your-gateway-host>"`.

Or run just the proxy and configure a tool manually with `logfire gateway serve`. See the [CLI reference](../../cli.md#ai-gateway-gateway) for details.

## See also

- [Embeddings](embeddings.md): discover and call embedding models through the gateway.
- [Prompt Management: Access and Prerequisites](../prompt-management/plan-requirements.md): prompt runs execute through the gateway and spend gateway budget.
- [Cost & Usage](../../../logfire-costs.md): plan tiers and how usage is billed.
