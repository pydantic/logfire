---
title: Use experimental feature flags
description: Define typed flags in code, target them consistently, and use them through Logfire or OpenFeature.
---

Use a feature flag when you need to turn behavior on or off without redeploying your application. The API is experimental: its import path and evaluation details may change while we learn from production use.

Install the feature-flag dependencies:

```bash
pip install 'logfire[feature-flags]'
```

To load values managed in Logfire, [create an API key](../use-api-keys.md#creating-api-keys) with the `project:read_variables` scope and set `LOGFIRE_API_KEY` before calling `logfire.configure()`. This is separate from `LOGFIRE_TOKEN`, which authorizes sending telemetry. Without a read-capable API key, flags use their code defaults. See [Remote variables](remote.md) for connection options.

Define the flag once, near the code it controls. The required default keeps your application working before Logfire receives configuration. If a later refresh fails, flags keep using the last loaded configuration and report a `stale` reason. Invalid configured values fall back to the code default.

Flag names currently share the managed-variable naming contract: use ASCII letters, digits, and underscores, without starting with a digit. For example, use `new_checkout` rather than `new-checkout`.

```python
import logfire
from logfire.experimental.feature_flags import feature_context, flag

logfire.configure()

new_checkout = flag(
    'new_checkout',
    default=False,
    description='Enable the redesigned checkout.',
)

with feature_context('account-123', attributes={'plan': 'team'}):
    print(new_checkout.value())
    #> False
```

The targeting key identifies the subject receiving the flag. Use a stable user or organization identifier so percentage rollouts consistently select the same outcome. Attributes let targeting rules select groups such as plans or regions. Context set by `feature_context()` also applies to other managed variables evaluated inside the block; pass `targeting_key` or `attributes` directly to an evaluation when it needs different values.

To inspect the selected variant, fallback reason, or error, call `details()`:

```python skip="true"
details = new_checkout.details(targeting_key='account-123')

print(details.value)
print(details.variant)
print(details.reason)
```

Feature-flag evaluation telemetry does not include the targeting key or targeting attributes. It records the flag, selected value and variant, selected value version, and the resolution reason. Native evaluation details use lowercase reasons such as `split`, `targeting_match`, `static`, `default`, or `error`.

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

Logfire validates a configured value before returning it. If validation fails, the evaluation returns the code default and reports a `type_mismatch` error in `checkout.details()`.

Pass `type=...` for any list, dict, set, tuple, or nullable default because Python cannot safely infer the complete type from those runtime values:

```python
from logfire.experimental.feature_flags import flag

allowed_regions = flag('allowed_regions', type=list[str], default=[])
```

## Test both outcomes

Override a flag in a test without changing remote configuration. Overrides apply in the current context to this flag's Logfire instance. Nest them to check both outcomes without relying on the remote value:

```python
from logfire.experimental.feature_flags import flag

new_checkout = flag('checkout_test', default=False)

with new_checkout.override_for_testing(False):
    with new_checkout.override_for_testing(True):
        assert new_checkout.value() is True

    assert new_checkout.value() is False
```

## Use the OpenFeature API

Install the optional adapter when you want to evaluate Logfire flags through OpenFeature's vendor-neutral API:

```bash
pip install 'logfire[openfeature]'
```

`LogfireProvider` implements the OpenFeature Python provider interface. Define each flag in Logfire first so its type and safe code default remain visible in your code, then register the provider explicitly:

```python
from openfeature import api

import logfire
from logfire.experimental.feature_flags import flag
from logfire.experimental.openfeature import LogfireProvider

logfire.configure()
flag('new_checkout', default=False)
api.set_provider_and_wait(LogfireProvider())

client = api.get_client()
enabled = client.get_boolean_value('new_checkout', False)
```

Creating a Logfire `Flag` does not change OpenFeature's global provider. This avoids surprising applications that already configure another provider or use separate provider domains.

`set_provider_and_wait()` waits for initial configuration and raises if it cannot load fresh values. Use `set_provider()` instead to initialize in the background; evaluations return the caller's default until initialization completes. The adapter reports later connection failures and recovery through OpenFeature provider events, using Logfire's existing refresh loop. Removing the adapter does not stop native Logfire flags or their connection.

On an evaluation error, OpenFeature returns the default supplied to the client call, which can differ from the flag's declared default. Evaluation telemetry records the value returned to the caller.

When evaluating through an OpenFeature client, use OpenFeature's own evaluation context. If both context APIs are active, OpenFeature's merged context is passed to Logfire as explicit evaluation input and takes precedence over `feature_context()`.

## Verify the flag

Run the application once, then find `feature_flag.evaluation` in Logfire. Confirm that it includes `feature_flag.key` and the outcome you expected.

## Troubleshoot the flag

- **The code default is always returned:** confirm the application has a `LOGFIRE_API_KEY` with the `project:read_variables` scope and that the flag name matches its name in Logfire.
- **A user changes variants between requests:** provide the same stable targeting key on every evaluation.
- **A targeting rule does not match:** pass every attribute used by the rule either through `feature_context()` or directly to the evaluation.

See [Targeting](targeting.md) for context precedence and [Remote variables](remote.md) for API-key setup.
