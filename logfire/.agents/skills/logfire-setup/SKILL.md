---
name: logfire-setup
description: Entry point for Pydantic Logfire — an observability, monitoring, and evals platform. Use this skill when the user asks to "set up Logfire", "add Logfire to my project", "get me set up properly with Logfire", "send as much data as would be useful", mentions Logfire without a specific scope, or their request spans more than one of instrumenting application code / monitoring infrastructure / evaluating AI behavior. If the request is clearly scoped to exactly one of those, fetch that specific skill directly instead of this one — this skill exists to route, not to duplicate their content.
---

# Set Up Logfire

Logfire is an observability platform built on OpenTelemetry, with several distinct product surfaces. Route to the specific skill for the surface the user actually wants — don't try to cover all of this from within this file.

| Surface | Covers | Skill |
|---------|--------|-------|
| App instrumentation | Traces, logs, metrics, and AI/agent spans from application code — Python, JavaScript/TypeScript, Rust, or any OpenTelemetry language | `logfire-instrumentation` |
| Infrastructure monitoring | Hosts, Docker, Kubernetes, database/queue/cache servers, cloud-provider metrics — no application code | `logfire-infrastructure` |
| Evals | Score AI/agent output against test-case datasets with `pydantic_evals` | `logfire-evals` |
| Querying telemetry | Search traces/logs/spans/metrics, summarize errors, find root cause | `logfire-query` |
| Live UI | Open project pages, the live view, trace links, or the Explore page in a browser | `logfire-ui` |
| Feature flags | Runtime-managed variables (`logfire.var()`, `logfire.template_var()`) | no dedicated skill yet — see the product's own docs |
| AI Gateway | Spend caps, failover, and routing for model calls (`logfire gateway`) | no dedicated skill yet — see the product's own docs |

## Route the Request

Fetch the matching skill(s) directly rather than acting on a guess here:

- "add logfire" / "instrument my app" / "add tracing, logging, or monitoring to my code" → `logfire-instrumentation`
- "monitor my host/server/Docker/Kubernetes/database" or infrastructure named by product rather than by code → `logfire-infrastructure`
- "set up evals" / "test my agent against cases" / "score with an LLM judge" → `logfire-evals`
- "query/search/find/summarize errors in Logfire" → `logfire-query`
- "open in Logfire" / "show me the live view" / "give me a link" → `logfire-ui`
- "get me set up properly" / "send as much data as would be useful" / no specific scope given, or the request genuinely spans more than one surface → fetch `logfire-instrumentation` and `logfire-infrastructure` together; add `logfire-evals` too if the project is an AI agent worth evaluating, not just observing.

If a request is genuinely ambiguous between two adjacent surfaces (e.g., "watch my Postgres" could mean Collector-level infrastructure metrics or app-level query instrumentation), ask one clarifying question rather than guessing which skill to load — loading the wrong one wastes the user's time reading instructions for a job they didn't ask for.

## What Every One of These Skills Shares

Each of `logfire-instrumentation`, `logfire-infrastructure`, and `logfire-evals` has its own Step 2 (Authenticate and Select the Exact Project) with the exact `logfire --non-interactive auth` / `projects use` / `whoami` commands and flags — they're independently runnable on purpose, so any one of them works standalone if that's the only skill fetched. Authenticating once resolves `whoami` for the rest of the session, so if a second skill from this table gets fetched afterward, its own Step 2 will report "already resolved" and can be skipped.

Never print, log, hard-code, commit, or echo a token or its credentials file, in any of these skills, at any point.
