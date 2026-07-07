# JavaScript / TypeScript Verification And Troubleshooting

Run the project's normal checks and at least one runtime smoke path after instrumentation.

## Static Checks

- Run the package's typecheck, build, lint, or test script when present.
- For monorepos, run checks for the modified workspace.
- Ensure imports match module format: ESM uses `import`, CommonJS uses `require`.
- Search client code and public env files for leaked write-token names or values.

Useful searches:

```bash
rg "LOGFIRE_TOKEN|NEXT_PUBLIC_.*LOGFIRE|VITE_.*LOGFIRE|Authorization=.*logfire|Authorization=.*pylf"
rg "@pydantic/logfire-node" src app pages
```

The second search should not find browser-only modules.

## Runtime Smoke Tests

Node:

1. Set `LOGFIRE_CONSOLE=true` and a token or `LOGFIRE_SEND_TO_LOGFIRE=false`.
2. Start through the instrumented script.
3. Trigger one request or job.
4. Confirm local console output or Logfire traces.

Next.js:

1. Confirm `instrumentation.ts` is in root or `src`.
2. Start the app with OTLP env vars set.
3. Load a server-rendered route or call a route handler.
4. If browser tracing was added, inspect browser network requests to `/logfire-proxy/v1/traces`.

Cloudflare:

1. Run the existing Wrangler dev script.
2. Trigger a Worker request.
3. Confirm `.dev.vars` has `LOGFIRE_TOKEN` locally and production uses `wrangler secret`.

Deno:

1. Run with `OTEL_DENO=true` and `--unstable-otel`.
2. Trigger a manual span or request path.

## Common Missing-Trace Causes

- Node instrumentation file is imported after Express, HTTP clients, database clients, or the app entrypoint.
- The start script was changed for `dev` but production uses a different uninstrumented script.
- The app is ESM but the preload was added as `--require` instead of `--import`.
- `LOGFIRE_TOKEN` is absent and local `.logfire` credentials are not configured.
- Browser code is trying to send directly to Logfire instead of a same-origin proxy.
- Next.js has `instrumentation.ts` in the wrong directory for the app structure.
- Vercel AI SDK calls are missing `experimental_telemetry: { isEnabled: true }`.
- Existing OpenTelemetry configuration exports to a different backend or creates a competing tracer provider.

## What To Report Back

Summarize:

- detected JS/TS runtimes and frameworks
- packages installed per workspace
- files changed for instrumentation and startup
- environment variables or secrets the user must set
- verification commands run and whether traces/log output were observed
- any unverified runtime path, especially production-only scripts or browser proxy deployment
