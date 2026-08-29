---
title: Coding Agent Skills
description: Use Pydantic's coding agent skills and plugins to give Claude Code, Codex, Cursor, OpenCode, Pi, and other agents up-to-date Logfire knowledge.
---

# Coding Agent Skills

If you're adding Logfire observability to your application with a coding agent, you can install the
Logfire skill from the [`pydantic/skills`](https://github.com/pydantic/skills) repository to give
your agent up-to-date framework knowledge.

Agent skills are packages of instructions and reference material that coding agents load on demand.
The Logfire skill provides agents with patterns and guidance for instrumenting Python,
JavaScript/TypeScript, and Rust applications, with auto-instrumentation for frameworks like
FastAPI, httpx, asyncpg, and more.

## Installation

### Claude Code

Install the [official Logfire plugin](https://claude.com/plugins/logfire) from the Anthropic
marketplace, which is available by default:

```bash
claude plugin install logfire@claude-plugins-official
```

The plugin bundles skills, commands, and an MCP server. Claude will use the relevant skills
automatically, or you can invoke a command directly:

```
/instrument
```

As an alternative, you can install from the [`pydantic/skills`](https://github.com/pydantic/skills)
marketplace, which bundles the Logfire skill alongside other Pydantic-maintained skills:

```bash
claude plugin marketplace add pydantic/skills
claude plugin install logfire@pydantic-skills
```

### Codex

Install the Pydantic marketplace in Codex:

```bash
codex plugin marketplace add pydantic/skills --ref main
```

Then enable plugins from the **Pydantic** marketplace. Either enable them in the Codex plugin UI, or run:

```bash
codex plugin add logfire@pydantic-skills
codex plugin add logfire-exporter@pydantic-skills
```

Two plugins are available:

| Plugin | Purpose |
| --- | --- |
| **Logfire** | Gives Codex Logfire skills and the hosted Logfire MCP server for instrumentation, querying, and opening UI views. |
| **Logfire Exporter** | Exports completed Codex turns and tool calls to Logfire as OpenTelemetry traces. |

!!! note
    Logfire Exporter requires a Logfire write token before it can export anything; see [Export Codex Activity to Logfire](codex-logfire-exporter.md) for the one-time setup.

These plugins solve different problems and can be installed together. After enabling **Logfire Exporter**,
restart Codex and run `/hooks` if Codex asks you to review or trust the new hooks.

See also:

- [Connect to MCP Server](mcp-server.md) for how the Logfire plugin configures MCP access.
- [Export Codex Activity to Logfire](codex-logfire-exporter.md) for exporter setup, configuration, and troubleshooting.

### OpenCode

[OpenCode](https://opencode.ai) discovers skills from `.agents/skills/`, so the cross-agent install
below works without extra configuration:

```bash
npx skills add pydantic/skills
```

OpenCode reads `SKILL.md` files from both the project directory and `~/.agents/skills/`, walking up
from the current directory to the git worktree root. Confirm what it picked up with:

```bash
opencode debug skill
```

!!! note
    OpenCode requires each skill's `name` field to match the directory containing its `SKILL.md`.
    The Logfire skills follow that rule, so they load unchanged.

### Pi

[Pi](https://pi.dev) implements the [Agent Skills standard](https://agentskills.io/specification)
and loads skills from `~/.agents/skills/` globally and `.agents/skills/` in your project, so the
cross-agent install works there too:

```bash
npx skills add pydantic/skills
```

Each skill is also available as a `/skill:<name>` command, for example `/skill:logfire-instrumentation`.

!!! note
    Pi only loads project-local skills after you trust the project. Approve the prompt on first
    run, or pass `--approve` to trust the files for a single run.

### Cross-Agent

Install the Logfire skill using the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add pydantic/skills
```

The CLI is interactive and lets you pick individual skills (e.g. `logfire-instrumentation` or
`logfire-query`) rather than installing the whole bundle.

This works with 30+ agents via the [agentskills.io](https://agentskills.io) standard, including
Claude Code, Codex, Cursor, OpenCode, and Pi.

### Library Skills

Logfire also ships its skill bundled with the package, so you can install it directly from your
project's dependencies via [library-skills.io](https://library-skills.io):

```bash
uvx library-skills        # Python
npx library-skills        # JavaScript/TypeScript
```

Add `--claude` to also install into `.claude/skills` alongside the default `.agents` directory.

## See also

- Source repository: [github.com/pydantic/skills](https://github.com/pydantic/skills)
- Open standards: [agentskills.io](https://agentskills.io), [library-skills.io](https://library-skills.io)
- Claude Code skills documentation: [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)
- Claude Code plugins documentation: [code.claude.com/docs/en/plugins](https://code.claude.com/docs/en/plugins)
