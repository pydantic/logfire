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

Add the Pydantic marketplace and install the plugin:

```bash
claude plugin marketplace add pydantic/skills
claude plugin install logfire@pydantic-skills
```

### Cross-Agent

Install the Logfire skill using the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add pydantic/skills
```

This works with 30+ agents via the [agentskills.io](https://agentskills.io) standard, including
Claude Code, Codex, Cursor, and Gemini CLI.

### Library Skills

Logfire also ships its skill bundled with the package, so you can install it directly from your
project's dependencies via [library-skills.io](https://library-skills.io):

```bash
uvx library-skills        # Python
npx library-skills        # JavaScript/TypeScript
```

Add `--claude` to install into `.claude/skills` instead of the default `.agents` directory.

## See also

- Source repository: [github.com/pydantic/skills](https://github.com/pydantic/skills)
- Open standards: [agentskills.io](https://agentskills.io), [library-skills.io](https://library-skills.io)
