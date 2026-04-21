---
title: "Access and Prerequisites"
description: "What a project needs in order to author, test, and ship prompts in Logfire."
---

# Access and prerequisites

Access to Prompt Management depends on a combination of plan eligibility and gateway availability.

- The feature requires a project on a plan that includes the Logfire **gateway**. The gateway is what executes prompt tests and what usage is billed against.
- Running prompts, including batch runs, spends gateway budget.
- Before a prompt can run, the project needs a configured gateway and a gateway API key the current user can access.

## Permissions

Prompt Management currently uses variable-level permissions:

| Capability | Permission |
|---|---|
| View templates, scenarios, settings, and run history | `read_variables` |
| Save versions | `write_variables` |
| Promote a version to a label | `write_variables` |
| Execute single or batch runs | `write_variables` |

Because run history includes model outputs, treat `read_variables` as sensitive if your prompts handle sensitive data.

For pricing details, plan tiers, and how gateway usage is metered, see [Cost & Usage](../../../logfire-costs.md). The gateway documentation in [Gateway Migration](../../../gateway-migration.md) covers the legacy-vs-integrated distinction that some projects may still be navigating.
