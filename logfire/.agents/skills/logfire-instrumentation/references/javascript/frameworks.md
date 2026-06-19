# JavaScript Framework Setup

This file is a compatibility index for older prompts that ask for the JS framework reference directly. For new instrumentation work, read [project-detection.md](./project-detection.md) first, then the runtime-specific reference.

## Runtime Routing

| Detected project | Primary reference | Runtime package |
| --- | --- | --- |
| Express, Fastify, Koa, Hono on Node, scripts, CLIs, workers outside edge runtimes | [node-runtime.md](./node-runtime.md) | `@pydantic/logfire-node` |
| Next.js server-side tracing | [nextjs.md](./nextjs.md) | `@vercel/otel` plus `logfire` for manual spans |
| React/Vite/browser tracing | [react-browser.md](./react-browser.md) | `@pydantic/logfire-browser` |
| Cloudflare Workers | [cloudflare-and-deno.md](./cloudflare-and-deno.md) | `@pydantic/logfire-cf-workers` plus `logfire` |
| Deno | [cloudflare-and-deno.md](./cloudflare-and-deno.md) | Deno OpenTelemetry plus `npm:logfire` |
| Vercel AI SDK | [ai-sdk.md](./ai-sdk.md) | Depends on Node or Next.js setup |

## Current Defaults

- Use `node --import ./instrumentation.js` for modern Node ESM preload. Use `--require` only for CommonJS.
- Browser code must send traces to a same-origin backend proxy. Never use `LOGFIRE_TOKEN`, `OTEL_EXPORTER_OTLP_HEADERS`, or write-token literals in browser bundles.
- Next.js server-side tracing should use `@vercel/otel`; do not use `@pydantic/logfire-node` as the primary Next server setup unless the app has a separate custom Node server.
- Cloudflare Workers wrap the exported handler with `instrument()` from `@pydantic/logfire-cf-workers`; import manual spans/logs from `logfire`.
