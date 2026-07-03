---
robots: noindex
title: "Migration from gateway.pydantic.dev"
description: "Historical reference: how the legacy gateway.pydantic.dev was migrated to the AI Gateway on Pydantic Logfire."
---

# Pydantic AI Gateway Has Moved to Pydantic Logfire

!!! tip "Looking for the current gateway docs?"
    For how to enable and use the AI Gateway in Logfire today — providers, API keys, routing, and spending controls — see the [AI Gateway overview](reference/advanced/gateway/index.md).

We consolidated the AI Gateway into Logfire. The legacy standalone gateway at [gateway.pydantic.dev](https://gateway.pydantic.dev/) **has been shut down**, and the gateway is now managed through your Logfire account. This page remains as a historical reference for users migrating from the legacy platform.

## Shutdown Timeline

| Date | Event |
|------|-------|
| **15 March 2026** | Self-service refunds became available in the legacy gateway platform |
| **13 April 2026 at 3pm UTC** | Legacy gateway fully shut down (end of life) |
| **End of April 2026** | Automatic refunds processed for any remaining balances |

The legacy gateway service has been shut down; [gateway.pydantic.dev](https://gateway.pydantic.dev/) now shows a migration notice. If you have an outstanding question about a refund or your old account, email us at [engineering@pydantic.dev](mailto:engineering@pydantic.dev).

## Why We Made This Change

Moving the gateway into Logfire unlocked a number of improvements:

- **Observability and gateway, side by side.** Because the gateway now lives in Logfire, you can instrument your LLM calls and trace them directly, with no context switching between separate products.
- **Tighter integration with features that use the gateway.** The LLM Playground and other Logfire features that rely on the gateway are now in the same place, making them easier to discover and use together.
- **Enterprise-grade controls, included.** The gateway now inherits Logfire's [enterprise features](enterprise.md) — including SSO, custom roles and permissions, and security group mapping — so teams with existing enterprise setups get those controls automatically.
- **One account, one billing relationship.** Rather than managing a separate balance on a separate platform, gateway usage is consolidated into your Logfire account alongside any other plan charges.
