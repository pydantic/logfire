---
name: logfire-setup
description: Route broad requests to set up Pydantic Logfire across application instrumentation, infrastructure, evals, frontend observability, Gateway, or coding agents. Use for "set up Logfire", "add Logfire to my project", "get me set up properly with Logfire", "send as much data as would be useful", mentions of Logfire without specific scope, or multi-surface requests; use the matching specialist directly for an already scoped request.
---

# Set Up Logfire

Load the specialist for the requested task. Proceed with reversible setup;
pause for browser consent, an ambiguous target, materially more telemetry or cost,
deployment changes, or destructive work.

## Step 1: Authenticate and Select the Exact Project

For frontend, Gateway, coding agents, query or UI work, load that specialist
first. Do not create an SDK write token just to route a request.

Read-only repository inspection does not require login. Before modifying the app
or sending telemetry, follow [Authenticate and Select the Exact Project](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md).
For standalone SDK setup, confirm the target with `project current` when configured.
If the wizard already prepared this project, reuse its target and send-only SDK write token.
Never broaden it. Mint a separate credential only if a later task needs one.

## Step 2: Understand the Repo

Read the repository instructions and identify the runtime and package manager.

| Surface | Covers | Skill |
|---------|--------|-------|
| App instrumentation | Traces, logs, metrics, and AI/agent spans from application code — Python, JavaScript/TypeScript, Rust, or any OpenTelemetry language | [`logfire-instrumentation`](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/SKILL.md) |
| Frontend observability | Browser errors, RUM, Web Vitals, and session replays | [`logfire-frontend`](https://pydantic.dev/.well-known/agent-skills/logfire-frontend/SKILL.md) |
| Infrastructure monitoring | Hosts, Docker, Kubernetes, database/queue/cache servers, cloud-provider metrics — no application code | [`logfire-infrastructure`](https://pydantic.dev/.well-known/agent-skills/logfire-infrastructure/SKILL.md) |
| Evals | Set up and run AI/agent evaluations against test-case datasets in Python or Node.js | [`logfire-evals`](https://pydantic.dev/.well-known/agent-skills/logfire-evals/SKILL.md) |
| Querying telemetry | Search traces/logs/spans/metrics, summarize errors, find root cause | [`logfire-query`](https://pydantic.dev/.well-known/agent-skills/logfire-query/SKILL.md) |
| Live UI | Open project pages, the live view, trace links, or the Explore page in a browser | [`logfire-ui`](https://pydantic.dev/.well-known/agent-skills/logfire-ui/SKILL.md) |
| Feature flags | Runtime-managed variables (`logfire.var()`, `logfire.template_var()`) | no dedicated skill yet — see the product's own docs |
| Application Gateway | Route an application's model calls through Pydantic AI Gateway | [`logfire-gateway`](https://pydantic.dev/.well-known/agent-skills/logfire-gateway/SKILL.md) |
| Coding agents | Record Claude/Codex sessions or configure coding-agent Gateway routing | [`logfire-coding-agents`](https://pydantic.dev/.well-known/agent-skills/logfire-coding-agents/SKILL.md) |

- With no specific scope, get one representative application service to verified first data. Incidental Docker/eval files do not expand the task. Route infrastructure-only repositories to `logfire-infrastructure`.
- If "monitor Postgres" could mean server metrics or application queries, ask which.

## Step 3: Fetch the Right Skill(s)

Load the selected specialist, not the entire catalog. In a CLI wizard handoff,
use that executable to read the release-matched instructions offline: for example,
`logfire-cli skill prompt logfire-instrumentation --no-input --output json`
returns `data.prompt`, and `skill read` returns the selected reference in
`data.contents`. Otherwise open the linked specialist or its installed copy.
A query or link request does not require an SDK write token.

Never print, log, or commit credentials. See the
[credential handoff instructions](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md#if-the-calling-skill-needs-another-credential)
if a later step needs a separate credential. After verification, share the clean
project link and report what you actually observed. With the CLI, use
`mcp link project --project <confirmed-project>` with `--no-input --output json`
and without `--open`; return `data.url`. Prefer the verified trace or
experiment link when available. If link creation fails, say so; never invent
a URL or treat creating one as proof of ingestion. Do not rerun
`project current` after a parent-prepared handoff.
