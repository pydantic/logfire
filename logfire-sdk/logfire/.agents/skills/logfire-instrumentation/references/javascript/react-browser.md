# React And Browser Instrumentation

Use this for browser-only telemetry in React, Vite, or other SPA projects. If the app is Next.js, read [nextjs.md](./nextjs.md) instead.

## Frontend Application Requirement

Browser telemetry sends directly to Logfire with a restricted public frontend application token. The token can report only for that application; it cannot read project data or choose another service identity. Never put an ordinary Logfire write token in browser code.

Open **Frontend → Applications**, create or select the browser application, and copy its regional base URL and restricted token. If that page is unavailable, explain that browser setup cannot continue with an ordinary write token and direct the user to [Logfire support](https://pydantic.dev/docs/logfire/get-started/help/).

## Install

```bash
npm install @pydantic/logfire-browser
```

Use `@pydantic/logfire-browser` 0.21.0 or later for `configureFrontend()`.
It enables auto-instrumentation and Web Vitals metrics by default. Set
`autoInstrumentations: false` to disable automatic instrumentation. Set
`rum: { webVitals: false }` to disable Web Vitals spans and metrics, or
`rum: { webVitals: { metrics: false } }` to keep Web Vitals spans without metrics. Nested capture options preserve unrelated defaults. Session
replay remains opt-in through the optional replay integration.

## Configure In Browser-Only Code

For React, add a provider mounted once near the app root. The restricted token is designed to be public and may be embedded in the client bundle or supplied through the app's public build/runtime configuration. Replace both placeholders before deploying:

```tsx
import * as logfire from '@pydantic/logfire-browser'
import { useEffect, useRef, type ReactNode } from 'react'

export function LogfireProvider({ children }: { children: ReactNode }) {
  const configured = useRef(false)

  useEffect(() => {
    if (!configured.current) {
      logfire.configureFrontend({
        baseUrl: '<generated-regional-base-url>',
        token: '<frontend-application-token>',
      })
      configured.current = true
    }
  }, [])

  return children
}
```

Mount this provider once at the app root and do not return the asynchronous SDK cleanup from its effect. The ref prevents React Strict Mode's development-only second effect setup from configuring Logfire twice. Tests, previews, or app shells that intentionally replace the whole telemetry setup should await the cleanup returned by `configureFrontend()` before configuring a replacement.

For non-React browser entrypoints, run the same generated configuration from the client entry file before adding manual spans. Do not set `serviceName`, `serviceNamespace`, or the environment; the frontend application pins those values at ingest.

## Optional Backend Proxy

A backend proxy is not required to hide the restricted frontend token. Preserve one when the application already uses it, or add one only when the application specifically needs its own authentication, origin checks, or rate limits. Use the lower-level `configure()` for custom proxy transports. Follow the browser SDK guide's [optional-proxy contract](https://pydantic.dev/docs/logfire/instrument/typescript/packages/browser/#optional-backend-proxy) and keep its existing security controls.

When maintaining a proxy, compare each request's `Origin` against an explicitly
configured allowed origin, such as `LOGFIRE_PROXY_ALLOWED_ORIGIN` (or the
application's existing equivalent). Reject requests when that configuration is
absent, the `Origin` header is missing, or it does not match. Do not derive the
allowed origin from the incoming request. Preserve the proxy's authentication
and rate limits as well; an origin check alone is not authentication.

## Manual Client Events

```ts
button.addEventListener('click', () => {
  logfire.info('checkout button clicked')
})
```

Report client errors:

```ts
window.addEventListener('error', (event) => {
  logfire.reportError('uncaught browser error', event.error, { filename: event.filename }, { tags: ['browser'] })
})

window.addEventListener('unhandledrejection', (event) => {
  logfire.reportError('unhandled browser rejection', event.reason, {}, { tags: ['browser'] })
})
```

## Browser-Specific Cautions

- Configure only in browser runtime code. Avoid importing `@pydantic/logfire-browser` from SSR modules.
- Use `diagLogLevel: logfire.DiagLogLevel.ALL` only during local troubleshooting.
- Browser `configureFrontend()` returns an async cleanup function. Await it in tests, previews, or app shells that intentionally replace the telemetry setup, but not in the root provider effect above.
- Browser does not install automatic pending-span processing; call `startPendingSpan()` explicitly for long operations.
- Avoid high-volume spans for every mouse movement, render, or keystroke.
