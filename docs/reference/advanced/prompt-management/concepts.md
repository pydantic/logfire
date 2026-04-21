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

!!! important "A version freezes the template — nothing else"
    Saving a version stores only the template text. If you test "v2" today and test "v2" again later, you will get v2's template but whatever settings are current at execution time.

For prompt testing workflows, see [Test Prompts](./scenarios.md).

## Identifiers you will see

Prompts carry two identifiers that matter in normal use.

| Identifier | Example | Where you see it |
|---|---|---|
| **Display name** | `Welcome Email` | Prompts list, page titles, search |
| **Slug** | `welcome-email` | URL path (`/prompts/welcome-email/`) |

!!! tip "Slug rules"
    Slugs must be 1–100 characters, lowercase letters and digits only, hyphens allowed.
