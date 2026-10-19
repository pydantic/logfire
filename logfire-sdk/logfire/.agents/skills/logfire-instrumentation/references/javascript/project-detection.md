# JavaScript / TypeScript Project Detection

Read this before editing a JS/TS project. Instrument every runtime in the app, not just the first `package.json` you find.

## Locate The Package Boundary

1. Find all `package.json` files, ignoring `node_modules`, build output, generated clients, and vendored examples unless the user explicitly targets them.
2. If the repo has workspaces, identify which workspace owns the app entrypoint. Install dependencies in that workspace.
3. Choose the package manager from lockfiles:
   - `pnpm-lock.yaml`: `pnpm add`
   - `yarn.lock`: `yarn add`
   - `bun.lock` or `bun.lockb`: `bun add`
   - `package-lock.json`: `npm install`
   - no lockfile: preserve the scripts' existing manager when obvious, otherwise use `npm install`
4. If a package already has a Logfire or OpenTelemetry setup, extend it instead of adding a duplicate provider.

## Detect Runtimes And Frameworks

Inspect dependencies, devDependencies, scripts, config files, and entrypoints.

| Signal | Treat as | Read |
| --- | --- | --- |
| `next`, `next.config.*`, `app/`, `pages/` | Next.js | [nextjs.md](./nextjs.md) |
| `express`, `fastify`, `koa`, Node server scripts, `src/server.*`, `src/app.*` | Node server | [node-runtime.md](./node-runtime.md) |
| `vite`, `react`, `@vitejs/*`, `src/main.tsx`, browser-only SPA | Browser app | [react-browser.md](./react-browser.md) |
| `wrangler.*`, `@cloudflare/workers-types`, scripts invoking `wrangler` | Cloudflare Workers | [cloudflare-and-deno.md](./cloudflare-and-deno.md) |
| `deno.json`, `deno.lock`, Deno task scripts | Deno | [cloudflare-and-deno.md](./cloudflare-and-deno.md) |
| `ai`, `@ai-sdk/*` | Vercel AI SDK calls | [ai-sdk.md](./ai-sdk.md) |
| Existing `@opentelemetry/*`, `@vercel/otel`, `instrumentation.ts`, `OTEL_*` env docs | Existing OTel | Extend current setup |

## Existing OpenTelemetry Rules

- Do not create a second global tracer provider in the same runtime.
- If `@vercel/otel` is present in Next.js, add Logfire OTLP env vars and use the `logfire` package for manual spans.
- If a Node app already has a custom `NodeSDK`, add Logfire exporters/processors only if the current SDK structure is clear. Otherwise ask before replacing custom OTel wiring.
- If OpenTelemetry env vars already point to another backend, preserve them unless the user explicitly wants Logfire to replace that backend. Prefer documenting the conflict over silently changing production export destinations.

## Entry Point Rules

- Node auto-instrumentation must be loaded before instrumented libraries are imported.
- Framework files that run in both server and browser contexts must not import `@pydantic/logfire-node` or read server secrets from client code.
- Browser instrumentation must run in browser-only modules (`'use client'`, client entrypoint, or dynamic import with SSR disabled).
- For monorepos, add one service name per deployable service, not one name for the whole repo.
