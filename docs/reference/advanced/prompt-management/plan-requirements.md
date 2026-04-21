---
title: "Plan Requirements for Prompt Management"
description: "Plan eligibility for Logfire Prompt Management and links to billing information."
---

# Plan requirements

Access to Prompt Management depends on a combination of plan eligibility and gateway availability.

- The feature requires a project on a plan that includes the Logfire **gateway**. The gateway is what the Run and batch-run actions execute against, and is also the cost boundary for model spend.
- Running prompts (single or batch) spends gateway budget. There is no per-prompt or per-project cost ceiling for batch runs today; see [Known limitations](./limitations.md#no-batch-cost-ceiling).
- Authoring and reading prompt metadata does not require gateway access, but it does require the relevant project permissions — `read_variables` lets a user view prompts, scenarios, versions, and run history; `write_variables` lets them edit and execute runs. See [Known limitations](./limitations.md#coarse-permissions) for the full capability mapping.

For pricing details, plan tiers, and how gateway usage is metered, see [Cost & Usage](../../../logfire-costs.md). The gateway documentation in [Gateway Migration](../../../gateway-migration.md) covers the legacy-vs-integrated distinction that some projects may still be navigating.
