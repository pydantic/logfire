---
title: "Prompt Management Concepts"
description: "The core objects in Prompt Management: prompts and versions."
---

# Concepts

Prompt Management revolves around two core objects: the prompt you author and the versions you save and promote.

### Prompt

A **prompt** is the unit you author and ship. It has a human-readable name, a URL slug, template text, and test settings such as model and tools.

Example: a prompt named *"Welcome Email"* with slug `welcome-email`. One prompt per concept your application consumes.

### Version

A **version** is an immutable snapshot of a prompt's template text. Versions are numbered sequentially (v1, v2, v3, …) and recorded with the author and timestamp. You save a version when you want a stable point to promote, compare against, or roll back to.

!!! important "A version freezes the template, nothing else"
    Saving a version stores only the template text. If you test "v2" today and test "v2" again later, you will get v2's template but whatever settings are current at execution time.

### Backing managed variable

Every prompt is backed by a managed variable. That backing variable is what your
application fetches, and it is where labels, targeting, and rollout rules live.

The backing variable name is derived from the prompt slug:

```text
prompt__<slug_with_underscores>
```

For example, a prompt with slug `welcome-email` has the backing variable
`prompt__welcome_email`.

Use Prompt Management to author the prompt and save versions. Use Managed
Variables to promote a version by moving labels such as `production`, `canary`,
or `staging`, or to configure rollout and targeting rules.

!!! note "The backing variable is system-managed"
    Names starting with `prompt__` are reserved for Prompt Management. Create and
    rename prompts from the Prompts page rather than creating `prompt__...`
    variables directly.

### Fragments and references

Prompts can compose reusable fragments with `@{...}@` references. A prompt can
reference a regular managed variable:

```handlebars
@{support_safety_rules}@
```

It can also reference another prompt through that prompt's backing variable:

```handlebars
@{prompt__support_style}@
```

Use composition for shared configuration that should have its own owner, version
history, or rollout. Use `{{...}}` template parameters for per-request inputs.

For prompt testing workflows, see [Test Prompts](./scenarios.md).

## Identifiers you will see

Prompts carry two identifiers that matter in normal use.

| Identifier | Example | Where you see it |
|---|---|---|
| **Display name** | `Welcome Email` | Prompts list, page titles, search |
| **Slug** | `welcome-email` | URL path (`/prompts/welcome-email/`) |

!!! tip "Slug rules"
    Slugs must be 1–100 characters, lowercase letters and digits only, hyphens allowed.
