# Client-Side Feature Flags with OFREP

Logfire's managed variables can serve as feature flags for client-side applications like web frontends, mobile apps, and edge services. The [OFREP (OpenFeature Remote Evaluation Protocol)](https://openfeature.dev/docs/reference/other-technologies/ofrep/) endpoints let any OpenFeature-compatible client evaluate variables without the Python SDK.

This guide shows how to set up a **JavaScript/TypeScript web application** using the official OpenFeature Web SDK and OFREP provider. The same approach works for any language with an [OpenFeature SDK and OFREP provider](https://openfeature.dev/ecosystem).

## Prerequisites

1. **Create your variable** in the Logfire UI (*Settings → Managed Variables → New variable*) and turn on the **External** toggle. Without *External*, OFREP returns `FLAG_NOT_FOUND` for that variable — see [External Variables and OFREP](../reference/advanced/managed-variables/external.md).
2. **Publish a value.** A freshly-created variable has no versions. Open the variable, click *Edit* on the `latest` label, pick a value, and create a version. Until there's a published version, OFREP still returns `FLAG_NOT_FOUND`.
3. **Create an API key** with the `project:read_external_variables` scope. This restricted scope is safe to ship in client code — it only exposes variables you've explicitly marked as external.

## Installation

Install the OpenFeature Web SDK and OFREP provider:

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
    yarn add @openfeature/web-sdk @openfeature/ofrep-web-provider
    ```

## Setup

Initialize the OpenFeature provider once at application startup. The OFREP provider connects to your Logfire project's OFREP endpoint and handles authentication via your API key.

```typescript
import { OFREPWebProvider } from '@openfeature/ofrep-web-provider'
import { OpenFeature } from '@openfeature/web-sdk'

const LOGFIRE_API_KEY = 'your-api-key'  // project:read_external_variables scope
const LOGFIRE_API_HOST = 'logfire-api.pydantic.dev'  // or your self-hosted API host

const provider = new OFREPWebProvider({
  // ``@openfeature/ofrep-web-provider`` appends ``/ofrep/v1/evaluate/flags``
  // to this URL itself, so ``baseUrl`` is the parent prefix — not the full
  // OFREP path. See the pitfall note below.
  baseUrl: `https://${LOGFIRE_API_HOST}/v1`,
  fetchImplementation: (input, init) => {
    // Start from whatever headers the library set on the Request (the
    // library clones the Request into ``input`` with a ``Content-Type``
    // header already attached — dropping it causes the backend to 422).
    const headers = new Headers(input instanceof Request ? input.headers : undefined)
    for (const [key, value] of new Headers(init?.headers).entries()) {
      headers.set(key, value)
    }
    headers.set('Authorization', `Bearer ${LOGFIRE_API_KEY}`)
    headers.set('Content-Type', 'application/json')
    return fetch(input, { ...init, headers })
  },
})

// Seed the context *before* registering the provider so the initial bulk
// evaluation posts a valid ``{"context": {...}}`` body. See "Evaluation
// context" below.
await OpenFeature.setProviderAndWait(provider, { targetingKey: 'anonymous' })
```

!!! note "API key in client-side code"
    The `project:read_external_variables` scope is designed to be safe for client-side use. It only grants read access to variables you've explicitly marked as external. Keep sensitive configuration in internal (non-external) variables, which are inaccessible with this scope.

!!! warning "Get the `baseUrl` right"
    The OFREP provider library appends `/ofrep/v1/evaluate/flags` (or `/evaluate/flags/{key}`) to `baseUrl` itself, so `baseUrl` is the parent prefix — **not** the full OFREP path. Pass `\`https://${apiHost}/v1\``, and the library makes requests to `https://<host>/v1/ofrep/v1/evaluate/flags`. If you see 404s on URLs like `https://<host>/v1/ofrep/v1/ofrep/v1/evaluate/flags` in the network tab, the `/ofrep/v1` suffix was included twice — drop it from `baseUrl`.

## Evaluation context

Every OFREP request must carry a non-empty `context` with a `targetingKey`. The backend returns **422** (and the provider goes into a fatal `ERROR` state) if the context is missing, so the recommended flow is:

1. Seed the provider with a stub `{ targetingKey: 'anonymous' }` via `setProviderAndWait` at startup, or
2. Delay `setProvider` until auth has resolved a real user identifier.

Once the user is authenticated, swap the context in:

```typescript
await OpenFeature.setContext({
  targetingKey: userId,  // stable per-user identifier (user id, email, …)
  plan: 'enterprise',
  region: 'us-east',
})
```

The `targetingKey` ensures the same user always lands in the same variant bucket for rollouts. Any additional attributes become inputs for [conditional rules](../reference/advanced/managed-variables/ui.md#targeting-with-conditional-rules) configured in the Logfire UI — for example, routing `enterprise` plan users to a specific label.

## Evaluating Flags

Use the OpenFeature client to evaluate flags. The client provides typed methods for different value types:

```typescript
const client = OpenFeature.getClient()

// Boolean flag
const showNewFeature = client.getBooleanValue('show_new_feature', false)

// String value (e.g., a theme or prompt)
const theme = client.getStringValue('ui_theme', 'light')

// Number value
const maxRetries = client.getNumberValue('max_retries', 3)

// Get detailed evaluation info
const details = client.getStringDetails('ui_theme', 'light')
console.log(details.value)    // resolved value
console.log(details.variant)  // label name (e.g., "production", "canary")
console.log(details.reason)   // evaluation reason (e.g., "TARGETING_MATCH", "SPLIT")
```

The second argument to each method is the **default value**, returned when the flag can't be evaluated (e.g., network error, flag not found). Use `getBooleanDetails` / `getStringDetails` instead of `getBooleanValue` / `getStringValue` when you need to distinguish "defaulted because of an error" from "the real value happens to be the same as the default" — `details.reason === 'ERROR'` tells you the provider couldn't resolve the flag.

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

Wrap your application with the `OpenFeatureProvider` and read flags through `useBooleanFlagValue` / `useStringFlagValue` / `useNumberFlagValue`. These hooks re-render their component automatically when the provider becomes ready, the flag configuration changes server-side, or the evaluation context changes — you don't need a custom subscription layer.

```tsx
import {
  OpenFeatureProvider,
  useBooleanFlagValue,
  useContextMutator,
  useStringFlagDetails,
} from '@openfeature/react-sdk'
import { useEffect } from 'react'

// In your app root - registered once, *after* auth has resolved.
function App() {
  return (
    <AuthProvider>
      <OpenFeatureProvider>
        <OpenFeatureContextSync />
        <MyComponent />
      </OpenFeatureProvider>
    </AuthProvider>
  )
}

// Keep the evaluation context synced with the logged-in user.
// Prefer ``useContextMutator`` over calling ``OpenFeature.setContext``
// directly once ``<OpenFeatureProvider/>`` is mounted - it updates the
// domain-scoped context used by the hooks.
function OpenFeatureContextSync() {
  const { user } = useAuth()
  const { setContext } = useContextMutator()

  useEffect(() => {
    setContext({
      targetingKey: user?.id ?? 'anonymous',
      ...(user?.email ? { email: user.email } : {}),
    }).catch(() => undefined)
  }, [user?.id, user?.email, setContext])

  return null
}

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

!!! tip "Register the provider once, gated on auth"
    Call `OpenFeature.setProviderAndWait(provider, { targetingKey })` at most **once** per session. If you re-register, any cached values from the first registration are discarded and the provider may spend a render cycle in `ERROR` while it recovers. If your app has no user context before login, either seed with `targetingKey: 'anonymous'` as shown above, or only call `setProviderAndWait` after auth has resolved a real user id.

## Debugging

When flag evaluation isn't returning what you expect, run through this checklist in order.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `details.errorCode === 'FLAG_NOT_FOUND'` for every flag | Provider's initial bulk evaluation failed, so its cache is empty. | Check the network tab for a failed request to `/v1/ofrep/v1/evaluate/flags`. Usually a 422 (see next row). |
| `details.errorCode === 'FLAG_NOT_FOUND'` for one specific flag only | The variable isn't marked **External**, or it doesn't have a published version. | Toggle *External* on in the variable settings, then create a version under the `latest` label. |
| Network tab shows `422 Unprocessable Entity` on `/evaluate/flags` | Request body was missing `context` or the `Content-Type: application/json` header. | Ensure `setContext` (or `setProviderAndWait(provider, context)`) runs before the first evaluation, and your `fetchImplementation` preserves the `Content-Type` header — see the snippet in [Setup](#setup). |
| Network tab shows `404 Not Found` on `/ofrep/v1/ofrep/v1/...` | `baseUrl` has `/ofrep/v1` and the provider library appended another. | Use `baseUrl: \`https://${apiHost}/v1\`` — the library adds the `/ofrep/v1` suffix itself. |
| Network tab shows `401 Unauthorized` | API key missing, expired, or lacking the right scope. | Create a new key with `project:read_external_variables` in *Settings → API keys*. |
| Value never updates after `setContext` | Still reading via `OpenFeature.setContext` / `OpenFeature.getClient` instead of the React-SDK hooks. | Use `useContextMutator().setContext` and `useBooleanFlagValue` / `useStringFlagValue` inside the `<OpenFeatureProvider/>` subtree so React re-renders on context changes. |
| All requests 200, but `details.reason === 'DEFAULT'` | The provider cache is warm but no rule matched the given context. | Open the variable's *Targeting* tab and verify the rules match the attributes you're sending (`targetingKey`, `plan`, …). |

### Inspecting a single evaluation from the devtools

If you want to confirm the backend is returning what you expect independently of the SDK, make a raw OFREP request from the browser console:

```javascript
await fetch('https://logfire-api.pydantic.dev/v1/ofrep/v1/evaluate/flags/show_new_feature', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${API_KEY}`,
  },
  body: JSON.stringify({
    context: { targetingKey: 'user-123' },
  }),
}).then(r => r.json())
```

A `200` with `{ value, reason, variant }` means the backend is wired correctly; any client-side failure to see the value is an SDK-layer issue (cache cold, wrong context, etc.).

## Full Example

Here's a complete setup combining initialization, context, and evaluation:

```typescript
import { OFREPWebProvider } from '@openfeature/ofrep-web-provider'
import { OpenFeature } from '@openfeature/web-sdk'

function buildProvider(apiKey: string, apiHost: string) {
  return new OFREPWebProvider({
    baseUrl: `https://${apiHost}/v1`,
    fetchImplementation: (input, init) => {
      const headers = new Headers(input instanceof Request ? input.headers : undefined)
      for (const [key, value] of new Headers(init?.headers).entries()) {
        headers.set(key, value)
      }
      headers.set('Authorization', `Bearer ${apiKey}`)
      headers.set('Content-Type', 'application/json')
      return fetch(input, { ...init, headers })
    },
  })
}

// Register once, seeded with an anonymous targetingKey so the initial
// bulk evaluation carries a valid context.
export async function initFeatureFlags(apiKey: string, apiHost: string) {
  await OpenFeature.setProviderAndWait(buildProvider(apiKey, apiHost), {
    targetingKey: 'anonymous',
  })
}

// Swap to a real identifier after the user logs in.
export async function setUserContext(userId: string, attributes: Record<string, string> = {}) {
  await OpenFeature.setContext({
    targetingKey: userId,
    ...attributes,
  })
}

// Evaluate flags anywhere in your app.
export function getFeatureFlags() {
  const client = OpenFeature.getClient()
  return {
    showNewDashboard: client.getBooleanValue('show_new_dashboard', false),
    pricingTier: client.getStringValue('pricing_tier_config', 'standard'),
    maxUploadSize: client.getNumberValue('max_upload_size_mb', 10),
  }
}
```

## Other Languages and Platforms

OpenFeature provides SDKs and OFREP providers for many languages. You can use the same Logfire OFREP endpoint with any of them:

| Platform | SDK | OFREP Provider |
|----------|-----|---------------|
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

Authenticate with an `Authorization: Bearer <api-key>` header using a key with `project:read_external_variables` scope. Both endpoints require `Content-Type: application/json` and a non-empty `context`.
