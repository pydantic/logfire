---
title: "Logfire Release Notes & Changelog"
description: "List of official Logfire release notes and changelogs. Get an overview of the latest features, changes, and updates."
---

## Upgrading from 4.x to 5.x

### Install the managed variables extra

If your application uses `logfire.variables`, include the `variables` extra when upgrading:

```bash
pip install --upgrade 'logfire[variables]'
```

Keep the extra in your project's dependencies, not only in a one-off install command. A plain `logfire` install does not include the managed-variable dependencies. Without them, imports such as `from logfire.variables import Variable` fail with: "Using managed variables requires the `pydantic_handlebars` and `pydantic` packages".

### Use valid code defaults for managed variables

In the current 5.x SDK, a JSON-serializable code default goes through serialization and validation against the variable's declared type, just like a remotely supplied value. A deliberately invalid sentinel, such as a Pydantic model created with `model_construct()` that violates a field constraint, therefore resolves with reason `validation_error`, not `code_default`. The result still contains the raw default as its fallback value, along with the validation exception.

If your code alerts on `validation_error`, it will alert every time resolution falls back to that invalid default, even with no remote value configured. Replace it with a valid default, or explicitly allow the sentinel in the variable's type. Review resolution-reason checks as part of the upgrade.

--8<-- "CHANGELOG.md"
