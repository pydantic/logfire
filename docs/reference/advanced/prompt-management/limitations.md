---
title: "Prompt Management: Known Limitations"
description: "The current scope, known rough edges, and planned improvements for Logfire Prompt Management."
---

# Known limitations

This page is the honest list of what the current implementation does *not* do yet. Other pages link here rather than restating the caveats inline. Items will be trimmed as they are addressed.

## Versioning is template only {#versioning-is-template-only}

Saving a version freezes the **prompt template string** and nothing else. Model, tools, API format, route, stream, and model settings all live in a separate autosaved row that updates immediately on every edit. Concretely:

- Pinning a version today does not pin the model that was active when it was saved.
- The "compare versions" view diffs template text only. Changes to tools or model settings are invisible in the diff.
- Rolling back a version does not roll back model or tool changes.

Every **run** does snapshot the settings that were live at execution time, so past runs remain reproducible for audit. But the forward-looking version concept is narrower than in some competing products, which freeze the full callable.

A decision on whether to widen versions or introduce an explicit "publish" action is open. Until then, treat "version" in Logfire as "template history".

## Rollout and serving state are on the Variables page {#serving-state-is-on-variables}

Authoring happens on `/prompts/<slug>/`. Labels (for example, `production`, `canary`), percentage rollouts, and the *"which version is currently serving?"* view live on the Managed Variables detail page for the same prompt (`/variables/prompt__<slug>/`).

This means shipping a new version to production is a two-page flow:

1. Save the new version on the Prompts page.
2. Move the `production` label on the Managed Variables page.

There is no "Currently serving: vN" indicator on the Prompts page today. A read-only mirror is planned so that authors can see serving state without leaving the authoring surface. The full cross-page "ship to production" walkthrough will be published alongside that change.

## SDK callers see the internal variable name {#sdk-callers-see-the-internal-name}

Prompts are stored as rows in `variable_definitions` with `kind='prompt'`, which means the SDK reaches them via `logfire.var(name='prompt__<slug_with_underscores>', ...)`. The `prompt__` prefix and the hyphen-to-underscore conversion are implementation details that currently leak to SDK callers.

A dedicated `logfire.prompt(slug=...)` helper is planned. Once it ships, the prefix and the slug normalization will become internal, and example SDK code in this section will be updated to use it.

In the meantime, the recommended pattern is the one shown in the Logfire [demo integration](https://github.com/pydantic/platform/blob/main/src/demos/logfire_demo/demo_prompt_variables_pydantic_ai.py) — call `logfire.var` with the explicit internal name and treat the returned payload as the prompt template.

Related rough edge: because the derivation `slug.replace('-', '_')` is lossy, a slug of `order-confirmation` and a slug of `order_confirmation` would collide on the internal name. Pick one style per project. A validator to disallow the ambiguity is planned.

## SDK rendering helper is not yet shipped {#sdk-rendering-helper}

Both the Logfire UI preview and the server Run use pydantic-handlebars and agree on the full grammar documented in [Template reference](./template-reference.md). The SDK does not yet ship a wrapper for that renderer — the demo integration hand-rolls a simple `{{variable}}` regex that supports only flat identifier substitution. In particular, the demo renderer does **not** support dotted paths or block helpers.

An official `logfire.render_prompt(template, variables)` helper is planned so SDK-rendered output matches exactly what Logfire shows in the editor and executes on Run. Until that lands, if your templates use dotted paths or block helpers, either consume them through a locally vendored pydantic-handlebars rather than the regex demo, or restrict templates you ship via the SDK to flat `{{variable}}` references.

## Coarse permissions {#coarse-permissions}

Today, every Prompt Management capability is gated by one of two variable-level permissions:

| Capability | Gated by |
|---|---|
| View template, scenarios, settings | `read_variables` |
| View run history (including model output) | `read_variables` |
| Save a draft version | `write_variables` |
| Promote a version to a label (on the Variables page) | `write_variables` |
| Execute a single run | `write_variables` |
| Execute a batch run (up to 500 cases) | `write_variables` |

Two consequences to note:

- Run history includes the model's output for each case. Any user with `read_variables` can read the outputs of every prompt run in the project. If your prompts see sensitive inputs, treat `read_variables` as sensitive.
- Iterating on a draft and promoting to production share the same bit. There is no separate `run_prompts` or "publish" permission today.

Dedicated `read_prompts` / `write_prompts` / `run_prompts` permission names are on the roadmap so that enterprise projects can split author, publisher, and runner roles cleanly.

## No batch-run cost ceiling {#no-batch-cost-ceiling}

Batch runs call the gateway once per case, up to 500 cases per batch call, with a small amount of concurrency. There is currently no per-user or per-project spend cap, no approval flow, and no second-confirmation before large runs. Each batch spends real gateway budget.

Before running a batch, double-check:

- the scenario and variable mapping you selected,
- the model and model settings on the prompt, and
- the size of the linked dataset (you can cap with `max_cases`).

A batch-run cost ceiling is on the roadmap.

## Gateway prerequisites require leaving the Prompts page {#gateway-prerequisites}

Before a prompt can Run, the project needs a configured gateway and a gateway API key the current user can access. If those are missing — unsupported plan, gateway disabled, no keys, or the selected key is unavailable — the prerequisite card on the Prompts page explains what is needed, but each recovery path requires leaving the Prompts page for the relevant settings screen.

Inline repair (for example, a "Create gateway key" modal on the Prompts page) is on the roadmap. In the interim, project admins should expect a one-time funnel of 2–3 settings pages before their first Run.

## Roadmap

The short list of tracked improvements:

- SDK: `logfire.prompt(slug=...)` helper and `logfire.render_prompt()` rendering wrapper.
- UI: read-only "Currently serving: vN" indicator on the Prompts page.
- Product: decision on versioning scope (narrow to "template history" or widen with a publish action).
- Permissions: split `read_prompts` / `write_prompts` / `run_prompts` from the generic variables permissions.
- Guardrails: a cost ceiling for batch runs.
- UX: inline gateway-key repair on the Prompts prerequisite card; hide the Prompts nav entry for ineligible plans.

If any of these land in a way that changes the docs above, the related page will be updated and this list trimmed.
