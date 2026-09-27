---
title: "Send your first AI Gateway request"
description: "Choose a provider, get a project API key, and verify a request through the Logfire AI Gateway."
---

# Send your first AI Gateway request

You can send a model request through the Gateway without changing the SDK your application uses. The **Connect** tab gives you a working example for your region, provider, model, and project.

If you only want to observe calls sent directly to a model provider, [instrument your application](../../../integrations/llms/index.md) instead. The Gateway sits in the request path and forwards calls to a provider.

## Before you start

- Create a Logfire organization and project. An organization admin must enable Gateway and set up a provider; other members can then use **Connect**.
- Decide who pays the model provider:
  - **Built-in provider**: Logfire supplies the upstream credentials. Calls draw from a prepaid balance. Activation may ask for a payment method and set up auto-recharge; eligible promotional credit may allow activation without one. Review the amounts and terms shown in the UI.
  - **Your provider**: [add a bring-your-own-key provider](byok-providers.md). Your provider bills you directly; you do not need a Logfire payment method for that route.

## Set up a route

1. In Logfire, select your organization and open **AI Engineering → Gateway**.
2. If Gateway is not enabled, choose **Enable recommended setup**. It enables Gateway, configures telemetry, installs recommended protections, and creates a first API key. If built-in providers need a payment method, you can add one or choose **Add BYOK provider** instead.
3. Open **Connect**. If it says **Choose how to connect**, select **Add a payment method** for built-in providers or **Add your own provider**. If it says **Built-in provider access needs activation**, open **Providers** to activate access or add your own provider. You cannot send a request until one route is available.
4. Under **Connect through**, choose the provider or [Gateway endpoint](endpoints.md) you want to call. A direct provider is enough for your first request.

## Get a credential and send a request

1. Under **Get your credential**, use the key for the project in your current Connect session. The page can create a key for that project when you get the credential; it can also use an existing key. If you need a key for another project, open that project's **API Keys** page before returning to Connect.
2. Click **Get your credential** to download a small file containing the Gateway URL and API key, or view and copy the credential on the page. Treat the key as a secret: put it in a local environment variable or secret manager, not source control. This is a **Gateway API key**, not the upstream provider key used to configure a BYOK provider.
3. Under **Connect**, choose **Copy the prompt for your AI coding agent** or a snippet for your SDK and copy it. The SDK snippet includes your region's URL and the selected route. If necessary, use **Customize connection** to change the model. After you reveal a key, a generated snippet may contain its plaintext value: do not commit or share the copied snippet. The coding-agent prompt uses a local credential file instead of putting your key in the chat.
4. Run the snippet or use **Try in playground**. The first request may incur upstream model charges or draw from your built-in prepaid balance.

The route URL has this shape:

```text
https://gateway-us.pydantic.dev/proxy/<route>/chat/completions
```

For an EU organization, use `https://gateway-eu.pydantic.dev/proxy` instead. Do not substitute a URL from another region; **Connect** supplies the correct one. Routes can be provider slugs or endpoint slugs. The URL path and SDK depend on the provider's API format, so use the generated snippet rather than assuming every provider speaks OpenAI's API.

## Verify it worked

**Connect** shows request progress after you send a call. You can also open **Gateway → Overview** for usage and, if telemetry is enabled, open the selected Logfire project to inspect the trace. Gateway telemetry can include request and response content; review your [protections](protect-data.md) and telemetry settings before sending sensitive production data.

## Troubleshooting

- **No providers available:** ask an organization admin to activate a built-in provider or [add your own](byok-providers.md). A provider assigned to an endpoint must also be active.
- **401 or 403:** check that you used a Gateway API key for the intended project, not your upstream provider key, and that the key has not expired.
- **Model not listed:** choose a model the selected provider serves, or enter its model identifier where the UI allows it. Model availability and pricing can differ by provider.
- **No pricing data:** a BYOK provider with **Require pricing data** enabled rejects unpriced requests. Add a price in provider settings, choose a priced model, or change that setting if you accept requests without a known price. This setting is separate from whether the upstream provider charges you.
- **No trace:** check that Gateway telemetry is enabled for the project in **Gateway → Settings**. A successful request does not imply telemetry was configured.

Next, [add an endpoint](endpoints.md) for failover, [protect request data](protect-data.md), or [set a spending policy](spending-policies.md).
