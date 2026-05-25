---
title: Coding Agent Skills
description: Use Pydantic's coding agent skills and plugins to give Claude Code, Codex, Cursor, Gemini CLI, and other agents up-to-date Logfire knowledge.
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
codex plugin add codex-logfire-exporter@pydantic-skills
```

Two plugins are available:

| Plugin | Purpose |
| --- | --- |
| **Logfire** | Gives Codex Logfire skills and the hosted Logfire MCP server for instrumentation, querying, and opening UI views. |
| **Codex Logfire Exporter** | Exports completed Codex turns and tool calls to Logfire as OpenTelemetry traces. |

These plugins solve different problems and can be installed together. After enabling **Codex Logfire Exporter**,
restart Codex and run `/hooks` if Codex asks you to review or trust the new hooks.

See also:

- [Connect to MCP Server](mcp-server.md) for how the Logfire plugin configures MCP access.
- [Export Codex Activity to Logfire](codex-logfire-exporter.md) for exporter setup, configuration, and troubleshooting.

### Cross-Agent

Install the Logfire skill using the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add pydantic/skills
```

The CLI is interactive and lets you pick individual skills (e.g. `logfire-instrumentation` or
`logfire-query`) rather than installing the whole bundle.

This works with 30+ agents via the [agentskills.io](https://agentskills.io) standard, including
Claude Code, Codex, Cursor, and Gemini CLI.

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
