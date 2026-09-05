---
name: logfire-setup
description: Entry point for Pydantic Logfire — an observability, monitoring, and evals platform. Use this skill when the user asks to "set up Logfire", "add Logfire to my project", "get me set up properly with Logfire", "send as much data as would be useful", mentions Logfire without a specific scope, or their request spans more than one of instrumenting application code / monitoring infrastructure / evaluating AI behavior. If the request is clearly scoped to exactly one of those, fetch that specific skill directly instead of this one — this skill exists to route, not to duplicate their content.
---

# Set Up Logfire

Logfire is an observability platform built on OpenTelemetry, with several distinct product surfaces. This skill authenticates, orients, and routes you to the specific skill for the surface you actually need — don't try to cover install/instrument/verify detail from within this file.

Keep the user informed with short updates, but proceed through ordinary, reversible setup without asking approval — no clean tree, branch, commits, or plan needed, and no commands the user could run only because you chose not to. Pause only for: browser auth, a genuinely ambiguous app/project after inspection, materially increasing production telemetry or cost, deploy/infra changes, or destructive/unrelated work — then ask one concrete question. Never report a check, a score, or a run as verified without having actually confirmed it in this session.

## Step 1: Authenticate and Select the Exact Project

Auth comes first because everything after it depends on having a valid, confirmed connection to the exact right Logfire project: instrumenting or inspecting the repo before that is either wasted if the connection turns out wrong, or worse, ends up silently wired to the wrong project. Do not open, read, or run any project file until `whoami` confirms you're authenticated to the right project — nothing about this step requires knowing what's in the repo yet.

Check first — `uvx logfire --non-interactive whoami` (JS: `npx logfire whoami`) — and skip to Step 2 if it already reports the right project and region. Otherwise, full command sequence, flags, and gotchas (the `--non-interactive` requirement, why `auth` won't open a browser for you, the `LOGFIRE_TOKEN`-vs-credentials-file conflict, token-file safety): [Authenticate and Select the Exact Project](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md).

## Step 2: Understand the Repo

Read `AGENTS.md`/`CLAUDE.md`/`README.md` and skim the language, runtime, and package manager. Then match what you find against the table below to decide what to fetch next:

| Surface | Covers | Skill |
|---------|--------|-------|
| App instrumentation | Traces, logs, metrics, and AI/agent spans from application code — Python, JavaScript/TypeScript, Rust, or any OpenTelemetry language | [`logfire-instrumentation`](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/SKILL.md) |
| Infrastructure monitoring | Hosts, Docker, Kubernetes, database/queue/cache servers, cloud-provider metrics — no application code | [`logfire-infrastructure`](https://pydantic.dev/.well-known/agent-skills/logfire-infrastructure/SKILL.md) |
| Evals | Score AI/agent output against test-case datasets with `pydantic_evals` | [`logfire-evals`](https://pydantic.dev/.well-known/agent-skills/logfire-evals/SKILL.md) |
| Querying telemetry | Search traces/logs/spans/metrics, summarize errors, find root cause | [`logfire-query`](https://pydantic.dev/.well-known/agent-skills/logfire-query/SKILL.md) |
| Live UI | Open project pages, the live view, trace links, or the Explore page in a browser | [`logfire-ui`](https://pydantic.dev/.well-known/agent-skills/logfire-ui/SKILL.md) |
| Feature flags | Runtime-managed variables (`logfire.var()`, `logfire.template_var()`) | no dedicated skill yet — see the product's own docs |
| AI Gateway | Spend caps, failover, and routing for model calls (`logfire gateway`) | no dedicated skill yet — see the product's own docs |

- No specific scope given (e.g. "set up Logfire in this repo end to end")? Default to `logfire-instrumentation` for ordinary application code. Incidental Docker, Kubernetes, infrastructure, or eval files do not expand the initial setup: get one representative application service to verified first data, then offer the matching additional skill(s). If the repository is clearly infrastructure-only, route directly to `logfire-infrastructure` instead.
- A request already scoped to one surface ("monitor my Postgres server", "set up evals for this agent") → fetch that skill directly, skipping the rest of this table.
- Genuinely ambiguous between two adjacent surfaces (e.g. "watch my Postgres" could mean Collector-level infrastructure metrics or app-level query instrumentation)? Ask one clarifying question rather than guessing — loading the wrong skill wastes the user's time reading instructions for a job they didn't ask for.

## Step 3: Fetch the Right Skill(s)

Fetch the skill(s) identified in Step 2 now, for the actual install/instrument/verify steps. Each one's own authenticate step still runs its own `whoami` check first — that's what confirms it's the same project and region resolved here, not an assumption carried over — and only then skips the rest of its auth commands. They're independently fetchable on purpose, so this composes whether someone reaches a specific skill through this hub or on its own.

Never print, log, hard-code, commit, or echo a token, in any of these skills, at any point. The one exception — reading `.logfire/logfire_credentials.json`'s `token` key programmatically to hand a non-native-SDK application its write token, never to display it — is in [auth.md](https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md#if-the-calling-skill-needs-a-write-token-not-just-a-cli-session).
