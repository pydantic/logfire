---
title: "For platform and security engineers"
description: "A starting path for platform and security teams: strip sensitive data before it leaves your machines, choose where data is stored, run Logfire on your own infrastructure, and understand compliance, sign-in, and cost."
---

# For platform and security engineers

You're the person who has to answer "where does the data go, who can log in, what sensitive information leaves our machines, and what does it cost?" This path points you at the controls for each of those, plus the option to run Logfire on your own infrastructure.

Each link says why it's here.

## Your path

1. **[Scrub sensitive data](../how-to-guides/scrubbing.md)**: the SDK scans traces and logs and redacts likely-sensitive values (passwords, tokens, and personally identifiable information, or PII) *before* they're sent to Logfire. Start here to control exactly what leaves your machines and to add your own redaction rules. Note one gap the guide explains: LLM prompt and response content is not scrubbed by default, so use `include_content=False` when those messages may carry secrets.

2. **[Choose your data region](../reference/data-regions.md)**: Logfire stores data in separate US and EU regions, and you pick your region when you sign up. Your account in each region is separate, with its own login and data, and nothing is shared between them, so choose up front for data residency and local regulations; a project's data stays in its region.

3. **[Compliance](../compliance.md)**: Logfire is SOC 2 Type II certified and HIPAA compliant, offers business associate agreements (BAAs), and provides an EU region for GDPR. Use this page to request the SOC 2 report and other documentation.

4. **[Single sign-on (SSO) setup](../how-to-guides/sso-setup.md)**: let your team sign in through your existing identity provider (Microsoft Entra ID, Okta, or a Keycloak OpenID Connect (OIDC) provider) instead of separate Logfire logins. Available on Enterprise Cloud.

5. **[Self-hosted Logfire](../reference/self-hosted/overview.md)**: run the whole platform inside your own infrastructure when data can't leave your network at all. Covers production requirements, installation, and day-to-day operations.

6. **[Billing and usage](../logfire-costs.md)**: understand what's metered (every span, log, and metric you send), the free monthly allowance, and the per-million rate above it, so cost holds no surprises.

## Related

- **[Sampling](../how-to-guides/sampling.md)**: keep a representative fraction of traffic instead of every trace, to control both volume and cost.
- **[Environments](../how-to-guides/environments.md)**: separate staging from production data within a project.
