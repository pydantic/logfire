---
title: Use experimental feature flags
description: Define boolean flags in code, target them consistently, and inspect how each value was selected.
---

Use a feature flag when you need to turn behavior on or off without redeploying your application. The API is experimental: its import path and evaluation details may change while we learn from production use.

Install the managed-variables dependencies:

```bash
pip install 'logfire[variables]'
```

Define the flag once, near the code it controls. The required default keeps your application working before Logfire receives configuration or whenever configuration is unavailable.

```python
import logfire
from logfire.experimental.feature_flags import feature_context, feature_flag

logfire.configure(send_to_logfire=False)

new_checkout = feature_flag(
    'new_checkout',
    default=False,
    description='Enable the redesigned checkout.',
)

with feature_context('account-123', attributes={'plan': 'team'}):
    print(new_checkout.is_enabled())
    #> False
```

The targeting key identifies the subject receiving the flag. Use a stable user or organization identifier so percentage rollouts consistently select the same outcome. Attributes let targeting rules select groups such as plans or regions. Context set by `feature_context()` also applies to other managed variables evaluated inside the block; pass `targeting_key` or `attributes` directly to an evaluation when it needs different values.

To inspect the selected variant, version, fallback reason, or error, call `evaluate()`:

```python skip="true"
details = new_checkout.evaluate(targeting_key='account-123')

print(details.value)
print(details.label)
print(details.reason)
```

Feature-flag evaluation telemetry does not include the targeting key or targeting attributes. It records the flag, selected value and variant, selected value version, and a standardized reason such as `split`, `targeting_match`, `static`, `default`, or `error`.

## Verify the flag

Run the application once, then find `feature_flag.evaluation` in Logfire. Confirm that it includes `feature_flag.key` and the outcome you expected.

## Troubleshoot the flag

- **The code default is always returned:** confirm the application has a `LOGFIRE_API_KEY` with the `project:read_variables` scope and that the flag name matches its name in Logfire.
- **A user changes variants between requests:** provide the same stable targeting key on every evaluation.
- **A targeting rule does not match:** pass every attribute used by the rule either through `feature_context()` or directly to the evaluation.

See [Targeting](targeting.md) for context precedence and [Remote variables](remote.md) for API-key setup.
