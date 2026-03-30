---
title: "Migrating from Pydantic AI Gateway"
description: "How to migrate from the legacy gateway.pydantic.dev to the AI Gateway on Pydantic Logfire."
---

# Pydantic AI Gateway is Moving to Pydantic Logfire

We're consolidating the AI Gateway into Logfire. This means [gateway.pydantic.dev](https://gateway.pydantic.dev/) is being deprecated, and the gateway is now managed through your Logfire account.

## Shutdown Timeline

| Date | Event |
|------|-------|
| **15 March 2026** | Self-service refunds available in the legacy gateway platform |
| **8 April 2026 at 3pm UTC** | Legacy gateway fully shut down (end of life) |
| **By end of April 2026** | Automatic refunds processed for any remaining balances |

**Please migrate before 8 April 2026.** If you need help, email us at [engineering@pydantic.dev](mailto:engineering@pydantic.dev).

## Why We Made This Change

Moving the gateway into Logfire unlocks a number of improvements:

- **Observability and gateway, side by side.** Because the gateway now lives in Logfire, you can instrument your LLM calls and trace them directly, with no context switching between separate products.
- **Tighter integration with features that use the gateway.** The LLM Playground and other Logfire features that rely on the gateway are now in the same place, making them easier to discover and use together.
- **Enterprise-grade controls, included.** The gateway now inherits Logfire's [enterprise features](enterprise.md) — including SSO, custom roles and permissions, and security group mapping — so teams with existing enterprise setups get those controls automatically.
- **One account, one billing relationship.** Rather than managing a separate balance on a separate platform, gateway usage is consolidated into your Logfire account alongside any other plan charges.

---

## Frequently Asked Questions

### What happens to my current balance?

From **15 March 2026**, you can request a refund of your remaining balance via the button in the [legacy gateway platform](https://gateway.pydantic.dev). The refund will be issued to the original payment method you used.

If you do not request a refund manually, any outstanding credits will be refunded automatically before the end of April 2026.

### Do I need to create a new account?

Yes, you'll need to sign up at [logfire.pydantic.dev](https://logfire.pydantic.dev) if you don't already have an account.

### Do I need to pay for Logfire to access the gateway?

No. Every new Logfire account starts on the Personal plan, which is free. You don't need to upgrade your Logfire plan to use the gateway, but you will need to add a credit card on the Personal plan for gateway-related charges.

### Do I need to add a credit card?

It depends on your plan:

- **Personal plan** (free): Yes, you'll need to add a credit card to use the gateway.
- **Team or Growth plans**: No — you already have a card on file from your plan subscription, and that card will be used for gateway charges.

### How do I set up the gateway on Logfire?

1. Go to [logfire.pydantic.dev](https://logfire.pydantic.dev).
2. Choose a region and create an account.
3. Add a credit card if you're on the Personal plan.
4. Go to your organization's Gateway settings and create an API key.
5. Update your application to use the new API key.

### I'm using Pydantic AI — what do I need to change?

Make sure you have an up-to-date version of Pydantic AI installed, then swap your API key for the one generated in Logfire. If you're using the `gateway/` provider prefix (e.g., `Agent('gateway/openai:gpt-4o')`), this is all you need to change:

```bash
export PYDANTIC_AI_GATEWAY_API_KEY="pylf_v..."
```

### Does anything carry over from PAIG Console?

No. This is a clean start — usage history, project settings, and API keys do not transfer. You'll configure everything fresh on Logfire.

### Can you do the migration for me?

Not right now, but if you'd like help, email us at [engineering@pydantic.dev](mailto:engineering@pydantic.dev).

### What if I have questions or need help?

Reach out to us at [engineering@pydantic.dev](mailto:engineering@pydantic.dev) and we'll be happy to help you through the transition.
