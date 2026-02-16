# Client-Side Feature Flags with OFREP

Logfire's managed variables can serve as feature flags for client-side applications like web frontends, mobile apps, and edge services. The [OFREP (OpenFeature Remote Evaluation Protocol)](https://openfeature.dev/docs/reference/other-technologies/ofrep/) endpoints let any OpenFeature-compatible client evaluate variables without the Python SDK.

This guide shows how to set up a **JavaScript/TypeScript web application** using the official OpenFeature Web SDK and OFREP provider. The same approach works for any language with an [OpenFeature SDK and OFREP provider](https://openfeature.dev/ecosystem).

## Prerequisites

1. **Create your variables** in the Logfire UI (Settings > Variables) and mark them as **external** — see [External Variables and OFREP](../reference/advanced/managed-variables/external.md)
2. **Create an API key** with the `project:read_external_variables` scope — this restricted scope is safe to use in client-side code since it only exposes variables you've explicitly marked as external

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
  baseUrl: `https://${LOGFIRE_API_HOST}/v1/ofrep/v1`,
  fetchImplementation: (input, init) =>
    fetch(input, {
      ...init,
      headers: {
        ...Object.fromEntries(new Headers(init?.headers).entries()),
        Authorization: `Bearer ${LOGFIRE_API_KEY}`,
      },
    }),
})

OpenFeature.setProvider(provider)
```

!!! note "API key in client-side code"
    The `project:read_external_variables` scope is designed to be safe for client-side use. It only grants read access to variables you've explicitly marked as external. Keep sensitive configuration in internal (non-external) variables, which are inaccessible with this scope.

## Setting Evaluation Context

Set the evaluation context to enable targeting and deterministic rollouts. The `targetingKey` ensures that the same user always gets the same variant:

```typescript
await OpenFeature.setContext({
  targetingKey: userId,
  // Additional attributes for targeting rules
  plan: 'enterprise',
  region: 'us-east',
})
```

Any attributes you include in the context can be used by [override rules](../reference/advanced/managed-variables/ui.md#targeting-with-override-rules) configured in the Logfire UI. For example, you could route all `enterprise` plan users to a specific label.

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

The second argument to each method is the **default value**, returned when the flag can't be evaluated (e.g., network error, flag not found).

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

## Full Example

Here's a complete setup combining initialization, context, and evaluation:

```typescript
import { OFREPWebProvider } from '@openfeature/ofrep-web-provider'
import { OpenFeature } from '@openfeature/web-sdk'

// Initialize once at app startup
function initFeatureFlags(apiKey: string, apiHost: string) {
  const provider = new OFREPWebProvider({
    baseUrl: `https://${apiHost}/v1/ofrep/v1`,
    fetchImplementation: (input, init) =>
      fetch(input, {
        ...init,
        headers: {
          ...Object.fromEntries(new Headers(init?.headers).entries()),
          Authorization: `Bearer ${apiKey}`,
        },
      }),
  })
  OpenFeature.setProvider(provider)
}

// Set context when user authenticates
async function setUserContext(userId: string, attributes: Record<string, string> = {}) {
  await OpenFeature.setContext({
    targetingKey: userId,
    ...attributes,
  })
}

// Evaluate flags anywhere in your app
function getFeatureFlags() {
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

Authenticate with an `Authorization: Bearer <api-key>` header using a key with `project:read_external_variables` scope.
