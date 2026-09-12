---
title: Use experimental feature flags
description: Define typed flags in code, target them consistently, and use them through Logfire or OpenFeature.
---

Use a feature flag when you need to turn behavior on or off without redeploying your application. The API is experimental: its import path and evaluation details may change while we learn from production use.

Install the feature-flag dependencies:

```bash
pip install 'logfire[feature-flags]'
```

Define the flag once, near the code it controls. The required default keeps your application working before Logfire receives configuration or whenever configuration is unavailable.

Flag names currently share the managed-variable naming contract, so use a valid Python identifier such as `new_checkout` rather than `new-checkout`.

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

To inspect the selected variant, fallback reason, or error, call `details()` (or the initial boolean API's `evaluate()` alias):

```python skip="true"
details = new_checkout.details(targeting_key='account-123')

print(details.value)
print(details.variant)
print(details.reason)
```

Feature-flag evaluation telemetry does not include the targeting key or targeting attributes. It records the flag, selected value and variant, selected value version, and the resolution reason. The Python evaluation details use standardized OpenFeature reasons such as `SPLIT`, `TARGETING_MATCH`, `STATIC`, `DEFAULT`, or `ERROR`.

## Validate structured flag values with Pydantic

Use `flag()` for strings, numbers, lists, and structured configuration. A Pydantic model makes the expected shape explicit and gives the rest of your application a fully typed value:

```python
from pydantic import BaseModel

from logfire.experimental.feature_flags import flag


class CheckoutConfig(BaseModel):
    provider: str
    retries: int


checkout = flag(
    'checkout',
    default=CheckoutConfig(provider='stripe', retries=2),
)

config = checkout.value()
print(config.provider)
#> stripe
```

Logfire validates a configured value before returning it. If validation fails, the evaluation returns the code default and reports OpenFeature's `TYPE_MISMATCH` error in `checkout.details()`.

Pass `type=...` when Python cannot safely infer the complete type from the default, such as an empty list or `None`:

```python
from logfire.experimental.feature_flags import flag

allowed_regions = flag('allowed_regions', type=list[str], default=[])
```

## Use the OpenFeature API

`LogfireProvider` implements the OpenFeature Python provider interface. Register it explicitly when you want to evaluate Logfire flags through OpenFeature's vendor-neutral API. Define each flag in Logfire first so its type and safe code default remain visible in your code:

```python
from openfeature import api

from logfire.experimental.feature_flags import LogfireProvider, feature_flag

feature_flag('new_checkout', default=False)
api.set_provider(LogfireProvider())

client = api.get_client()
enabled = client.get_boolean_value('new_checkout', False)
```

Creating a Logfire `Flag` does not change OpenFeature's global provider. This avoids surprising applications that already configure another provider or use separate provider domains.

## Verify the flag

Run the application once, then find `feature_flag.evaluation` in Logfire. Confirm that it includes `feature_flag.key` and the outcome you expected.

## Troubleshoot the flag

- **The code default is always returned:** confirm the application has a `LOGFIRE_API_KEY` with the `project:read_variables` scope and that the flag name matches its name in Logfire.
- **A user changes variants between requests:** provide the same stable targeting key on every evaluation.
- **A targeting rule does not match:** pass every attribute used by the rule either through `feature_context()` or directly to the evaluation.

See [Targeting](targeting.md) for context precedence and [Remote variables](remote.md) for API-key setup.
