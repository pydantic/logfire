# JavaScript / TypeScript Installation And Environment

Use the package manager detected in [project-detection.md](./project-detection.md). Install packages in the package or workspace that owns the runtime.

## Package Matrix

| Runtime | Install |
| --- | --- |
| Node.js server, worker, CLI, script | `@pydantic/logfire-node @opentelemetry/auto-instrumentations-node` |
| Next.js server-side tracing | `@vercel/otel logfire` |
| Browser/React/Vite client tracing | `@pydantic/logfire-browser` |
| Cloudflare Workers in-process tracing | `@pydantic/logfire-cf-workers logfire` |
| Deno | usually no package install; import `npm:logfire` for manual spans |
| Vercel AI SDK | no Logfire-specific package beyond the runtime setup; ensure `ai` telemetry is enabled in calls |

`@pydantic/logfire-node` expects OpenTelemetry packages as peers. If the package manager reports unmet `@opentelemetry/*` peers, install the reported packages rather than suppressing the warning.

## Environment Variables

Node.js and Cloudflare read Logfire-specific environment values. `LOGFIRE_TOKEN` is optional for local Node.js development specifically: `@pydantic/logfire-node` falls back to `.logfire/logfire_credentials.json` when it's unset, same as the Python SDK. Cloudflare has no equivalent fallback (see [cloudflare-and-deno.md](./cloudflare-and-deno.md)), so set it explicitly there always; for Node.js, set it explicitly only to override the local one — a different token, or production, where it should be a separately-minted token per [auth.md](../auth.md)'s "If the calling skill needs a write token" section.

```bash
LOGFIRE_TOKEN=your-write-token
LOGFIRE_SERVICE_NAME=checkout-api
LOGFIRE_SERVICE_VERSION=1.0.0
LOGFIRE_ENVIRONMENT=development
```

Node.js also supports:

```bash
LOGFIRE_CONSOLE=true
LOGFIRE_MIN_LEVEL=info
LOGFIRE_SEND_TO_LOGFIRE=if-token-present
LOGFIRE_TRACE_SAMPLE_RATE=0.1
LOGFIRE_BASE_URL=https://logfire-api.pydantic.dev
```

Next.js, Deno, and other platform OpenTelemetry integrations use OTLP variables:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
```

Use endpoint-specific variables when the platform requires them:

```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://logfire-api.pydantic.dev/v1/traces
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://logfire-api.pydantic.dev/v1/metrics
```

## Secret Placement

- Put `LOGFIRE_TOKEN` in server-only env files, deployment secrets, or Worker secrets.
- Do not create `NEXT_PUBLIC_LOGFIRE_TOKEN`, `VITE_LOGFIRE_TOKEN`, `PUBLIC_LOGFIRE_TOKEN`, or any public write-token variable.
- For browser code, create a frontend application and use its generated regional trace URL and restricted public token. Never reuse `LOGFIRE_TOKEN` or another ordinary write token in the browser.
- A frontend application token is intentionally restricted and public. Embed the generated token and trace URL directly in the client bundle, or supply them through the app's public build/runtime configuration (for example, `VITE_LOGFIRE_FRONTEND_TOKEN` and `VITE_LOGFIRE_TRACE_URL`). Do not deploy the generated example with placeholder values.
- Preserve an existing backend telemetry proxy. Add a new one only when the application needs its own authentication, origin checks, or rate limits; hiding the restricted token alone is not a reason.
- Update `.env.example` or documented env templates with placeholder values, not real tokens.
- If the app has separate frontend and backend packages, put the write token only in the backend package or hosting environment.

## Service Metadata

Set stable service names. Prefer deployable-unit names:

```ts
logfire.configure({
  serviceName: 'checkout-api',
  serviceVersion: process.env.npm_package_version,
  environment: process.env.NODE_ENV,
})
```

For browser telemetry, the frontend application pins the service name, namespace, and optional environment. Do not override them in browser SDK configuration. For Next.js, keep the server service name distinct from the frontend application name.
