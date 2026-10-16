# React And Browser Instrumentation

Browser errors, RUM, Web Vitals, route grouping, and session replays are owned by
the [frontend specialist](https://pydantic.dev/.well-known/agent-skills/logfire-frontend/SKILL.md).
Load that skill instead of initializing an ordinary SDK project write token.
It covers React/Vite and Next.js browser entrypoints, restricted frontend
application tokens, privacy controls, and verification.

For a Next.js server as well as its browser app, retain
[Next.js server instrumentation](./nextjs.md). Do not expand a browser-only task
to instrument a server.

## Group Pages By Route

The frontend specialist owns router integration and route-template grouping.
Follow its browser setup reference and the browser SDK's
[route-name contract](https://pydantic.dev/docs/logfire/instrument/typescript/packages/browser/#route-names)
rather than deriving templates from raw URLs.
