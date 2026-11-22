---
title: Use feature flags in a browser
description: Evaluate Logfire feature flags in a web app with OpenFeature and verify changes in an open page.
---

# Use feature flags in a browser

Change what a web app shows without deploying it again. The [OpenFeature Remote Evaluation Protocol (OFREP)](https://openfeature.dev/docs/reference/other-technologies/ofrep/) evaluates your flags in Logfire. The OpenFeature Web SDK keeps the evaluated values in the browser so your app can read them synchronously.

## Prerequisites

1. In your Logfire project, open **Feature Flags** and select **New flag**. Create a **Toggle**
   named `show_new_feature` and set it to **Off**. If the page is missing, enable **Feature Flags and Prompts UI**
   in **Early Access**.
2. On the flag's **Settings** tab, turn on **Allow restricted API keys to read this flag**
   under **Visibility**. Select **Make external** to confirm.
3. On **Use this flag**, select **Browser**, then **Create browser key**. Copy the key before closing
   the dialog. The key has only the `project:read_external_variables` scope. You can also create one
   in **API keys**. Expand **Advanced** and select **Read external managed variables within a project via OFREP**.

Anyone with the browser key can read any external flag in the project, and can supply their own
targeting attributes. Use external flags for public values such as UI choices. Enforce access
controls on your server.

## Install

=== "npm"

    ```bash
    npm install @openfeature/web-sdk @openfeature/ofrep-web-provider
    ```

=== "pnpm"

    ```bash
    pnpm add @openfeature/web-sdk @openfeature/ofrep-web-provider
    ```

=== "yarn"

    ```bash
    yarn add @openfeature/web-sdk @openfeature/core @openfeature/ofrep-web-provider @openfeature/ofrep-core
    ```

## Evaluate a flag

Run this at application startup in the browser. Replace the API key and use the host for your
Logfire region. Use `https://logfire-eu.pydantic.dev` for the EU region, or your API host if
you self-host Logfire.

```typescript
import { OFREPWebProvider } from '@openfeature/ofrep-web-provider'
import { OpenFeature, ProviderEvents } from '@openfeature/web-sdk'

const apiKey = 'YOUR_EXTERNAL_VARIABLES_KEY'
const apiUrl = 'https://logfire-us.pydantic.dev'

function createFlagProvider() {
  return new OFREPWebProvider({
    baseUrl: `${apiUrl}/v1`,
    headers: [['Authorization', `Bearer ${apiKey}`]],
    pollInterval: 60_000,
    cacheMode: 'disabled',
  })
}

try {
  await OpenFeature.setProviderAndWait(createFlagProvider(), { targetingKey: 'user-123' })
} catch (error) {
  console.warn('Could not load feature flags', error)
}

const client = OpenFeature.getClient()

function showFlag() {
  console.log('show_new_feature', client.getBooleanValue('show_new_feature', false))
}

client.addHandler(ProviderEvents.ConfigurationChanged, showFlag)
showFlag()
```

The first evaluation waits for the provider to finish loading. If the initial fetch fails,
or Logfire cannot evaluate the flag, the SDK returns the code default (`false` in this example).
After the provider loads the flags, the example keeps their values in memory for the current page
and checks for updates every 60 seconds. Choose a polling interval that fits how quickly open pages need to pick up a change.
If a later poll fails, the provider keeps the last evaluated values until a refresh succeeds.

## Verify a change

1. Open the browser console. With the flag off, the example prints `show_new_feature false`.
2. In Logfire, turn the flag on. Keep the page open. When the next successful poll gets the new
   value, the change handler prints `show_new_feature true`.

## Troubleshoot flag evaluation

If the example keeps printing `false`, check the browser's Network tab for requests ending in
`/ofrep/v1/evaluate/flags`. For a failed request, check the API host, key, and scope. If the
request succeeds but omits the flag, check its name and **Visibility** in the same project
where you created the key.

If the first fetch fails, the provider does not start polling. Resolve the startup error and reload
the page, or initialize a new provider to retry from within your app.

## Set targeting context

Replace `user-123` with a stable user or account ID for percentage rollouts. Pass additional
attributes for [targeting rules](../reference/advanced/managed-variables/targeting.md). When the
signed-in user changes, show the code defaults while you initialize a fresh provider for the new
context. If the fetch fails, keep showing the defaults. A failed `setContext()` can resolve and
leave the previous user's values in the existing provider.

```typescript
let showNewFeature = false
try {
  await OpenFeature.setProviderAndWait(createFlagProvider(), {
    targetingKey: signedInUser.id,
    plan: signedInUser.plan,
  })
  showNewFeature = client.getBooleanValue('show_new_feature', false)
} catch (error) {
  console.warn('Could not load flags for the signed-in user', error)
}
```

## React Integration

For React applications, OpenFeature provides a React SDK with hooks for flag evaluation:

=== "npm"

    ```bash
    npm install @openfeature/react-sdk
    ```

=== "pnpm"

    ```bash
    pnpm add @openfeature/react-sdk
    ```

=== "yarn"

    ```bash
    yarn add @openfeature/react-sdk
    ```

Wrap your application with the `OpenFeatureProvider` and use hooks in your components:

```tsx
import { OpenFeatureProvider, useBooleanFlagValue, useStringFlagDetails } from '@openfeature/react-sdk'

// In your app root
function App() {
  return (
    <OpenFeatureProvider>
      <MyComponent />
    </OpenFeatureProvider>
  )
}

// In any component
function MyComponent() {
  const showBanner = useBooleanFlagValue('show_banner', false)
  const theme = useStringFlagDetails('ui_theme', 'light')

  return (
    <div data-theme={theme.value}>
      {showBanner && <PromoBanner />}
      <p>Theme variant: {theme.variant}</p>
    </div>
  )
}
```

## Python

!!! note "Most Python services should use the Logfire SDK instead"
    OFREP exists to evaluate variables from **untrusted** environments. If you're shipping a Python **application to untrusted end users** (a desktop/CLI app, an on-device agent), use OFREP as shown below so the full variable configuration is never exposed. For a **trusted backend** you control, skip all of this and use the pull-based [`logfire.var()`](../reference/advanced/managed-variables/index.md). It evaluates locally with no per-flag network round-trip, and is the recommended path.

OpenFeature for Python is two separate installs, the core SDK and the OFREP provider:

```bash
pip install openfeature-sdk openfeature-provider-ofrep
```

```python skip="true"
from openfeature import api
from openfeature.contrib.provider.ofrep import OFREPProvider
from openfeature.evaluation_context import EvaluationContext

# base_url is the `/v1` root; the provider appends `/ofrep/v1/evaluate/flags/{key}`.
api.set_provider(
    OFREPProvider(
        base_url='https://logfire-us.pydantic.dev/v1',  # or 'https://logfire-eu.pydantic.dev/v1' for EU, or your self-hosted API host
        headers_factory=lambda: {'Authorization': 'Bearer YOUR_API_KEY'},
    )
)
client = api.get_client()
context = EvaluationContext(targeting_key='user-123')

show_new_feature = client.get_boolean_value('show_new_feature', False, evaluation_context=context)
```

The provider, like the OpenFeature client in general, evaluates one named flag at a time. To read **every** variable in a single call, `POST` the bulk endpoint directly with any HTTP client (there is no bulk method on the client). This example uses [`httpx`](https://www.python-httpx.org/) (`pip install httpx`), which is separate from the OpenFeature packages above:

```python skip="true"
import httpx

response = httpx.post(
    'https://logfire-us.pydantic.dev/v1/ofrep/v1/evaluate/flags',  # logfire-eu.pydantic.dev for EU
    headers={'Authorization': 'Bearer YOUR_API_KEY'},
    json={'context': {'targetingKey': 'user-123'}},
)
flags = response.json()['flags']  # [{'key', 'value', 'variant', 'reason'}, ...]
```

## Other Languages and Platforms

OpenFeature provides SDKs and OFREP providers for many languages. You can use the same Logfire OFREP endpoint with any of them:

| Platform | SDK | OFREP Provider |
|----------|-----|---------------|
| Python | [`openfeature-sdk`](https://pypi.org/project/openfeature-sdk/) | [`openfeature-provider-ofrep`](https://pypi.org/project/openfeature-provider-ofrep/) |
| JavaScript (Web) | [`@openfeature/web-sdk`](https://www.npmjs.com/package/@openfeature/web-sdk) | [`@openfeature/ofrep-web-provider`](https://www.npmjs.com/package/@openfeature/ofrep-web-provider) |
| JavaScript (Server) | [`@openfeature/server-sdk`](https://www.npmjs.com/package/@openfeature/server-sdk) | [`@openfeature/ofrep-provider`](https://www.npmjs.com/package/@openfeature/ofrep-provider) |
| Kotlin / Android | [OpenFeature Kotlin SDK](https://openfeature.dev/docs/reference/technologies/client/kotlin) | [OFREP Provider](https://github.com/open-feature/kotlin-sdk-contrib) |
| Swift / iOS | [OpenFeature Swift SDK](https://openfeature.dev/docs/reference/technologies/client/swift) | [OFREP Provider](https://github.com/open-feature/swift-sdk-contrib) |

See the [OpenFeature ecosystem page](https://openfeature.dev/ecosystem) for a full list.

The OFREP endpoint format is the same regardless of client:

```
POST https://<your-api-host>/v1/ofrep/v1/evaluate/flags/{flag_key}
POST https://<your-api-host>/v1/ofrep/v1/evaluate/flags
```

Both endpoints accept a JSON body with a `context` object containing `targetingKey` and any additional targeting attributes:

```json
{
  "context": {
    "targetingKey": "user-123",
    "plan": "enterprise",
    "region": "us-east"
  }
}
```

Authenticate with an `Authorization: Bearer <api-key>` header using a key with `project:read_external_variables` scope.
