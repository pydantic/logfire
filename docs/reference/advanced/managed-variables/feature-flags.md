---
title: Use experimental feature flags
description: Define typed flags in code, target them consistently, and use them through Logfire or OpenFeature.
---

Use a feature flag when you need to turn behavior on or off without redeploying your application. The API is experimental: its import path and evaluation details may change while we learn from production use.

The API follows [OpenFeature](https://openfeature.dev/), the vendor-neutral standard for feature flags. Evaluation details, reasons, and error codes use OpenFeature's names, so the optional [OpenFeature adapter](#use-the-openfeature-api) maps onto them one to one. Evaluation telemetry follows the OpenTelemetry [semantic conventions for feature flags](https://opentelemetry.io/docs/specs/semconv/feature-flags/), the standard attribute names for flag evaluations.

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

Targeting rules also see [baggage](../baggage.md), the key-value pairs that `logfire.set_baggage()` attaches to the current context. Use it to set an attribute once, higher up the call stack, for every flag evaluated below it. When an attribute comes from more than one place, attributes passed to the evaluation take precedence over `feature_context()`, which takes precedence over baggage. To ignore baggage, configure `LocalVariablesOptions` or `VariablesOptions` with `include_baggage_in_context=False`.

Baggage can also arrive with an incoming request from another service. If your application serves requests from callers you don't control and a targeting rule depends on baggage, configure `logfire.configure(distributed_tracing=False)`. Logfire then ignores incoming trace context and baggage, so only your own code can set the attributes that rules see.

Without a targeting key, a percentage rollout picks one variant for each trace. Every evaluation in the same request gets the same result, but the next request can get a different one. Logfire also warns once, because each user can switch between variants. Callers can't choose their variant by sending a chosen trace ID: Logfire combines the trace ID with a secret that only the running process knows.

To inspect the selected variant, fallback reason, or error, call `details()`:

```python skip="true"
details = new_checkout.details(targeting_key='account-123')

print(details.value)
print(details.variant)
print(details.reason)
```

Each evaluation creates a `feature_flag.evaluation` span. It records the flag, the serialized value and variant, the selected value version, and the reason. Values honor Pydantic serializers and Logfire scrubbing. The span also records the targeting key as `feature_flag.context.id`, so you can see why a user received a variant. It never records targeting attributes, which can contain customer data. To leave out the targeting key too, configure `include_targeting_key_in_telemetry=False`.

A flag value can include other managed variables with `@{name}@` references. The span then also records `composed_from`: the name, label, and version of each referenced variable, without their values. A change to a referenced variable changes what the flag serves without changing the flag's own version, so use `composed_from` to tell those values apart when you compare variants.

Native evaluation details use OpenFeature's reasons in lowercase, such as `split`, `targeting_match`, `static`, `default`, or `error`. A value set with [`override()`](#test-both-outcomes) reports `context_override`, the same reason that managed variables use. When the reason is `error`, `error_code` says why:

- `flag_not_found`: Logfire loaded configuration, but it has no flag with this name.
- `type_mismatch`: the configured value doesn't match the flag's type.
- `parse_error`: the configured value isn't valid JSON.
- `provider_not_ready` or `provider_fatal`: Logfire could not load configuration.

In each case the evaluation returns the code default.

Declaration schemas omit default annotations. Code defaults are recorded separately with Logfire scrubbing applied.

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

Validation is strict: Logfire does not convert one JSON type into another. A boolean flag rejects `1` and `"true"`, and an integer flag rejects `1.0` and `"1"`. This differs from `logfire.var()`, which converts compatible values. Check your configured values when you move a variable to a flag.

Pass `type=...` for any list, dict, set, tuple, or nullable default because Python cannot safely infer the complete type from those runtime values:

```python
from logfire.experimental.feature_flags import flag

allowed_regions = flag('allowed_regions', type=list[str], default=[])
```

## Tag downstream telemetry with the variant

Use the evaluation details as a context manager to tag everything inside the block with the selected variant. Logfire sets the `logfire.variables.<flag name>` baggage entry, and spans and logs created inside the block include it as an attribute. You can then compare variants, for example the latency of each checkout variant, by filtering on that attribute directly, without joining back to the evaluation span:

```python skip="true"
with new_checkout.details(targeting_key=user_id) as details:
    if details.value:
        render_new_checkout()
    else:
        render_old_checkout()
```

Calling `details()` or `value()` without `with` does not set baggage.

Baggage travels with distributed tracing. Downstream services receive the entry, and so do outgoing HTTP requests from instrumented clients, including requests to third-party APIs. This is usually what you want for analysis across services, but don't use it for variant names that must stay private. The OpenFeature adapter does not set baggage.

## Test both outcomes

Override a flag without changing remote configuration. Nest overrides to check both outcomes without relying on the remote value:

```python
from logfire.experimental.feature_flags import flag

new_checkout = flag('checkout_test', default=False)

with new_checkout.override(False):
    with new_checkout.override(True):
        assert new_checkout.value() is True

    assert new_checkout.value() is False
```

An override applies to this flag in the current context. Async tasks and `asyncio.to_thread()` calls started inside the block see it, and so do requests made with the Starlette or FastAPI `TestClient`. Threads that don't copy the context, such as a plain `threading.Thread` or a `concurrent.futures` executor, and other processes don't see it.

You can also override a flag in production, for example to give internal users a variant for one request. Evaluations report the `context_override` reason, so overridden values stay visible in telemetry.

### Test rollout rules

To test targeting rules and percentage rollouts, or to set values that every thread in the process sees, configure Logfire with local configuration instead of overrides:

```python
import logfire
from logfire.experimental.feature_flags import flag
from logfire.variables.config import (
    LabeledValue,
    Rollout,
    VariableConfig,
    VariablesConfig,
)

logfire.configure(
    send_to_logfire=False,
    variables=logfire.LocalVariablesOptions(
        config=VariablesConfig(
            variables={
                'beta_banner': VariableConfig(
                    name='beta_banner',
                    labels={'on': LabeledValue(version=1, serialized_value='true')},
                    rollout=Rollout(labels={'on': 1.0}),
                    overrides=[],
                ),
            }
        )
    ),
)

beta_banner = flag('beta_banner', default=False)
print(beta_banner.value())
#> True
```

Flags don't support `logfire.var()`'s `label=` argument for selecting a label by name. To serve a different value in each environment, add a targeting rule on the `deployment.environment` resource attribute instead.

## Use the OpenFeature API

Install the optional adapter when you want to evaluate Logfire flags through OpenFeature's vendor-neutral API:

```bash
pip install 'logfire[openfeature]'
```

`LogfireProvider` implements the OpenFeature Python provider interface. Register it to evaluate flags configured in Logfire; you don't need to declare them with Python's `flag()` function first:

```python
from openfeature import api

import logfire
from logfire.experimental.openfeature import LogfireProvider

logfire.configure()
api.set_provider_and_wait(LogfireProvider())

client = api.get_client()
enabled = client.get_boolean_value('new_checkout', False)
```

Native `flag()` declarations remain optional. If you declare a flag, the adapter also applies its Pydantic validation and serializers. Without a declaration, the OpenFeature method determines the expected value type. A missing flag returns `FLAG_NOT_FOUND` with the caller's default; a configured rollout that selects the default returns it without an error. Without a configured provider, for example without an API key, every flag returns the caller's default without an error. Neither case exports the caller's default in telemetry. These reads don't register native flags or emit code-first declaration events.

Creating a Logfire `Flag` does not change OpenFeature's global provider. This avoids surprising applications that already configure another provider or use separate provider domains.

`set_provider_and_wait()` waits for initial configuration and raises if it cannot load fresh values. Use `set_provider()` instead to initialize in the background; evaluations return the caller's default until initialization completes. The adapter reports later connection failures and recovery through OpenFeature provider events, using Logfire's existing refresh loop. Removing the adapter does not stop native Logfire flags or their connection.

On an evaluation error, OpenFeature returns the default supplied to the client call, which can differ from the flag's declared default. Error telemetry records the code and reason but omits the caller's default, which may not be protected by the flag's serializers.

When evaluating through an OpenFeature client, use OpenFeature's own evaluation context. If both context APIs are active, OpenFeature's merged context is passed to Logfire as explicit evaluation input and takes precedence over `feature_context()`.

## Verify the flag

Run the application once, then find `feature_flag.evaluation` in Logfire. Confirm that it includes `feature_flag.key` and the outcome you expected.

## Troubleshoot the flag

- **The code default is always returned:** confirm the application has a `LOGFIRE_API_KEY` with the `project:read_variables` scope and that the flag name matches its name in Logfire.
- **`details()` reports `flag_not_found`:** Logfire has no flag with this name. Create it in Logfire, or fix the name in your code.
- **A user changes variants between requests:** provide the same stable targeting key on every evaluation.
- **A targeting rule does not match:** pass every attribute used by the rule either through `feature_context()` or directly to the evaluation.

See [Targeting](targeting.md) for context precedence and [Remote variables](remote.md) for API-key setup.
