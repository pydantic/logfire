---
title: "Promote and Roll Out Prompts"
description: "How to promote prompt versions, canary changes, and roll back with managed-variable labels."
---

# Promote and roll out prompts

Prompt versions are served through the same labels, targeting, and rollout system
used by managed variables. The Prompts page is where you author and save prompt
versions. The Managed Variables page is where you decide which version production
traffic receives.

## Production workflow

The normal production workflow is:

1. Edit and test a prompt draft in Prompt Management.
2. Save a new prompt version.
3. Open the prompt's backing managed variable.
4. Move a serving label, such as `production`, to the new version.
5. Watch traces, runs, or evaluation results.
6. Move the label back if you need to roll back.

The backing variable name follows this pattern:

```text
prompt__<slug_with_underscores>
```

For example, the prompt slug `support-agent` maps to
`prompt__support_agent`.

## Promote a version

Suppose `support-agent` has:

| Version | Template |
|---|---|
| v1 | Current production support prompt |
| v2 | New prompt with clearer escalation instructions |

To promote v2:

1. Open **Managed Variables**.
2. Open `prompt__support_agent`.
3. On the **Values** tab, select the `production` label.
4. Edit from v2 or assign `production` to v2.
5. Save the label change.

Application code fetching the prompt with `logfire.prompt('support-agent')` (or
`logfire.template_prompt(...)`) and `label='production'` receives v2 on the next
resolution. No redeploy is required.

## Canary a prompt version

To canary a prompt version before moving all production traffic:

1. Save the new prompt as v2.
2. Create or move a `canary` label to v2.
3. Keep `production` pointing at v1.
4. In **Targeting**, route a small percentage of traffic to `canary` and the
   rest to `production`.

For example:

| Label | Weight |
|---|---:|
| `production` | 90% |
| `canary` | 10% |

Use a stable `targeting_key` when fetching the prompt so users or tenants keep a
consistent prompt assignment during the test. (Prompts resolve via
`LOGFIRE_API_KEY`, not the write token — see
[Use Prompts in Your Application](./application.md#fetch-and-render-the-prompt-from-the-sdk).)

```python skip="true"
from pydantic import BaseModel

import logfire

logfire.configure()


class SupportPromptInputs(BaseModel):
    customer_name: str
    tier: str


prompt_var = logfire.template_prompt(
    'support-agent',
    default='',
    inputs_type=SupportPromptInputs,
)

with prompt_var.get(
    SupportPromptInputs(customer_name='Maya Chen', tier='enterprise'),
    targeting_key='tenant-123',
) as resolved:
    prompt = resolved.value
```

If you explicitly pass `label='production'`, the SDK bypasses rollout weights and
always requests that label. Omit `label` when you want rollout percentages and
targeting rules to decide the served version.

## Target a segment

Use conditional targeting rules when a prompt should only change for a segment,
such as internal users, beta tenants, or enterprise customers.

For example:

| Condition | Routing |
|---|---|
| `plan` equals `enterprise` | `enterprise_support` = 100% |
| Default | `production` = 100% |

Then pass matching attributes from application code:

```python skip="true"
with prompt_var.get(
    SupportPromptInputs(customer_name='Maya Chen', tier='enterprise'),
    targeting_key='tenant-123',
    attributes={'plan': 'enterprise'},
) as resolved:
    prompt = resolved.value
```

## Roll back

Rollback is a label move:

1. Open the prompt's backing variable.
2. Move `production` back to the previous version.
3. Save.

The next prompt resolution gets the restored version. Existing traces still show
which prompt label and version were active for each request, so you can compare
behavior before and after the rollback.

## Measure the change

Prompt resolution happens inside Logfire's managed-variable system. When you use
the SDK context manager, downstream spans carry baggage that identifies the
served variable label and version.

Use that data to compare:

- response quality from online evaluations,
- escalation or task-success rates,
- latency and token usage,
- user or operator feedback,
- error rates by prompt label or version.

If your prompt also composes shared fragments with `@{...}@`, inspect traces to
see which fragment versions were involved in a resolution.

## What versions do and do not freeze

A prompt version freezes the prompt template text. It does not freeze:

- scenario messages or scenario variables,
- dataset mappings,
- model or tool settings used for UI test runs,
- composed managed-variable fragments,
- labels, rollout weights, or targeting rules.

This is intentional. Prompt versions give you stable template snapshots, while
labels and composed fragments let you change serving behavior without creating a
new prompt version for every operational adjustment.
