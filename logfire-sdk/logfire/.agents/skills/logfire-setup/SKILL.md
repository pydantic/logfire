---
name: logfire-setup
description: Route broad requests to set up Pydantic Logfire across application instrumentation, infrastructure, evals, frontend observability, Gateway, or coding agents. Use for "set up Logfire", "add Logfire to my project", "get me set up properly with Logfire", "send as much data as would be useful", mentions of Logfire without specific scope, or multi-surface requests; use the matching specialist directly for an already scoped request.
---

# Set Up Logfire

Route each explicitly requested surface to its specialist below; leave installation
and verification to those specialists. Do not expand an otherwise scoped request.

Proceed through ordinary, reversible setup with short updates without asking
approval; no clean tree, branch, commits, or plan is required. Pause for browser
auth, unresolved app/project ambiguity, material production cost or telemetry
increases, deploy/infra changes, or destructive/unrelated work, then ask one
concrete question. Report only
verification observed in this session.

## Step 1: Authenticate and Select the Exact Project

If the request is already scoped to frontend observability, application Gateway,
coding-agent setup, querying, or opening the UI, load that specialist from the
table below first. Its credential requirements differ from ordinary SDK
instrumentation; do not create a project write token merely to route the request.

For ordinary SDK instrumentation, confirm the exact project with `whoami`
before inspecting or running application files.

Use [Authenticate and Select the Exact Project](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md) to derive the CLI target from the supplied Logfire URL and run its target-aware `whoami` check with a verified CLI path — for JS/TS projects without `uv`, use the external-prefix npm fallback instead of plain `npx`, which can execute a repository-local binary. Skip to Step 2 if that already reports the right project and resolved `--region` or `--base-url` target; otherwise, continue through the full authentication and project-selection sequence there.


## Step 2: Understand the Repo

Read `AGENTS.md`/`CLAUDE.md`/`README.md` and skim the language, runtime, and package manager. Then match what you find against the table below to decide what to fetch next:

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
- A request already scoped to one surface ("monitor my Postgres server", "set up evals for this agent") → fetch that skill directly, skipping the rest of this table.
- Genuinely ambiguous between two adjacent surfaces (e.g. "watch my Postgres" could mean Collector-level infrastructure metrics or app-level query instrumentation)? Ask one clarifying question rather than guessing — loading the wrong skill wastes the user's time reading instructions for a job they didn't ask for.

## Step 3: Fetch the Right Skill(s)

Load the selected skill and follow its credential workflow. SDK specialists
verify the project with `whoami`; CLI specialists preserve prepared handoffs,
and query/UI skills can use existing native MCP access. Do not force one
authentication method across all surfaces.

Never print, log, hard-code, commit, or echo a token, in any of these skills, at any point. The one exception — reading `.logfire/logfire_credentials.json`'s `token` key programmatically to hand a non-native-SDK application its write token, never to display it — is in [auth.md](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md#if-the-calling-skill-needs-a-write-token-not-just-a-cli-session).
