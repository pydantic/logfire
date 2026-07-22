---
title: "For product and growth"
description: "A starting path for product and growth: turn features on and off without a redeploy, target changes to specific users, run experiments, and tie behavior back to real usage data."
---

# For product and growth

You want to change how the product behaves without waiting for an engineering release: flip a feature on for beta users, try a new prompt on 10% of traffic, or roll something back the moment it looks wrong. In Logfire, the tool for this is **feature flags** (Logfire calls them **managed variables**): configuration you define once in code but control from the Logfire UI, without redeploying.

Each link says why it's here.

## Your path

1. **[Feature flags](../reference/advanced/managed-variables/index.md)**: define a value once in your code with a sensible default, then change it live from the Logfire UI. A flag can be a simple on/off switch: turn a feature on or off, or target it to a specific group (beta opt-ins, internal users, a single customer) using your existing trace attributes as the targeting rules; or it can hold richer configuration such as a prompt.

2. **[Feature flags for web and mobile apps](../how-to-guides/client-side-feature-flags.md)**: serve those same flags to browser, mobile, and edge clients through OpenFeature (an open standard for feature flags) and its remote-evaluation protocol, OFREP, so any OpenFeature-compatible app can read them without the Python SDK.

3. **Tie changes back to usage**: every managed-variable resolution is recorded in your traces. That means you can correlate a flag or prompt change directly with what happened next (the basis for A/B tests and online experiments) using the same data your app already sends. See [Explore](../guides/web-ui/explore.md) to query that data in SQL and [Dashboards](../guides/web-ui/dashboards.md) to watch it over time.

!!! note "Product analytics, session replay, and real-user monitoring"
    Deeper product analytics, real-user monitoring (RUM, seeing performance and behavior from the actual browser) and session replay are on the roadmap and currently available to design partners. If that's what you need, [get in touch](../help.md).

## Try the full journey

- **[Roll out a prompt safely](../cookbook/roll-out-a-prompt-safely.md)**: change a live prompt for some traffic, watch the effect in your data, and roll it back if it gets worse.
