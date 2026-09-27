---
title: "Add your own provider to AI Gateway"
description: "Connect an upstream model provider with your own credentials and test it before sending Gateway requests."
---

# Add your own provider to AI Gateway

Bring your own key (BYOK) when you already have a model-provider account, want its billing to stay with that provider, or do not want to activate Logfire's built-in providers. A BYOK provider is available to Gateway requests once it has an active route. Your upstream provider bills you for the calls.

## Add a provider

You need organization-admin access and credentials for a supported provider. Have the provider's API key or other requested credential ready; Logfire stores it for forwarding requests, so use a credential with the access and spending limits you want at the upstream provider.

1. Open **AI Engineering → Gateway → Providers** and click **New BYOK provider** (or **Create BYOK provider** if the list is empty). From an empty **Connect** tab, you can also click **Add your own provider**.
2. Choose a **Provider type**. Use a named provider when possible; select a custom OpenAI- or Anthropic-compatible provider only if your plan permits custom endpoints.
3. Under **Connect provider**, enter the credential and any vendor-specific endpoint details. The default base URL is filled in for providers that have one.
4. Click **Test & continue**. This asks the provider for its models using the supplied configuration. A successful check confirms this connection test, not that every model or future request will work. If the check is unsupported or unavailable, the form offers **Continue without a passing check**; do that only if you can verify the route with a real request afterward.
5. Under **Name your provider**, choose a route name (slug), the URL segment after `/proxy/`. By default, **Add provider and create endpoint** creates an endpoint with the same slug. Under **Advanced options**, you can [assign the provider to an existing endpoint](endpoints.md) instead.
6. Save, then open **Connect**, select the new route, and [send a test request](first-request.md).

The provider's credential is different from the **Gateway API key** that your application sends to Logfire. Never put the upstream provider credential in a Gateway request or a public client.

!!! note "Custom endpoint restrictions"
    Custom base URLs and custom OpenAI- or Anthropic-compatible providers require Team, Growth, Enterprise, or self-hosted Logfire. On Personal, supported vendors must use their own permitted endpoint hosts. For example, an Azure or Vertex account-specific vendor endpoint can be valid, but an arbitrary proxy URL is not.

## Verify it worked

On **Providers**, confirm the new provider is active. On **Endpoints → your endpoint → Routing**, confirm that it is assigned and **Available for routing**. The route's **Connect** snippet should then target its slug.

## Troubleshooting

- If the connection test fails, recheck the provider type, base URL, credential permissions, and the provider's own model-listing API. A credential can be valid but lack permission to list models.
- If the test passes but inference fails, check the model identifier, upstream account quota, and the provider's error. **Test & continue** is not an inference test.
- If **Connect** says the endpoint has no active providers, confirm that the provider is active on **Providers** and **Available for routing** on the endpoint's **Routing** tab.
- If a model is unavailable because pricing is required, see [first-request troubleshooting](first-request.md#troubleshooting).

For one stable URL across multiple providers, [configure an endpoint](endpoints.md).
