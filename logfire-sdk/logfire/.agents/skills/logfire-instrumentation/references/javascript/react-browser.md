# React And Browser Instrumentation

Use this for browser-only telemetry in React, Vite, or other SPA projects. If the app is Next.js, read [nextjs.md](./nextjs.md) instead.

## Frontend Application Requirement

Browser telemetry sends directly to Logfire with a restricted public frontend application token. The token can report only for that application; it cannot read project data or choose another service identity. Never put an ordinary Logfire write token in browser code.

Open **Project settings → Frontend applications**, create or select the browser application, and copy its generated trace URL and token configuration. If that page is unavailable, explain that browser setup cannot continue with an ordinary write token and direct the user to [Logfire support](https://pydantic.dev/docs/logfire/get-started/help/).

## Install

```bash
npm install @pydantic/logfire-browser
```

## Configure In Browser-Only Code

For React, add a provider mounted once near the app root. The restricted token is designed to be public and may be embedded in the client bundle or supplied through the app's public build/runtime configuration. Replace both placeholders before deploying:

```tsx
import * as logfire from '@pydantic/logfire-browser'
import { useEffect, useRef, type ReactNode } from 'react'

export function LogfireProvider({ children }: { children: ReactNode }) {
  const configured = useRef(false)

  useEffect(() => {
    if (!configured.current) {
      logfire.configure({
        traceUrl: '<generated-regional-trace-url>',
        traceExporterHeaders: () => ({
          Authorization: 'Bearer <frontend-application-token>',
        }),
        autoInstrumentations: true,
        rum: { webVitals: true },
      })
      configured.current = true
    }
  }, [])

  return children
}
```

Mount this provider once at the app root and do not return the asynchronous SDK cleanup from its effect. The ref prevents React Strict Mode's development-only second effect setup from configuring Logfire twice. Tests, previews, or app shells that intentionally replace the whole telemetry setup should await the cleanup returned by `configure()` before configuring a replacement.

For non-React browser entrypoints, run the same generated configuration from the client entry file before adding manual spans. Do not set `serviceName`, `serviceNamespace`, or the environment; the frontend application pins those values at ingest.

## Optional Backend Proxy

A backend proxy is not required to hide the restricted frontend token. Preserve one when the application already uses it, or add one only when the application specifically needs its own authentication, origin checks, or rate limits. Follow the browser SDK guide's optional-proxy contract and keep its existing security controls.

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
- Browser `configure()` returns an async cleanup function. Await it in tests, previews, or app shells that intentionally replace the telemetry setup, but not in the root provider effect above.
- Browser does not install automatic pending-span processing; call `startPendingSpan()` explicitly for long operations.
- Avoid high-volume spans for every mouse movement, render, or keystroke.
