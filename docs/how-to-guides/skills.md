---
title: Claude Code Skills
description: Use Pydantic's Claude Code skills and plugins to streamline your workflow with Logfire.
---

# Claude Code Skills

[Skills](https://code.claude.com/docs/en/skills) are reusable prompt-driven capabilities for
[Claude Code](https://docs.anthropic.com/en/docs/claude-code). You create a `SKILL.md` file with
instructions, and Claude adds it to its toolkit — using it automatically when relevant, or on demand
via `/skill-name`.

Pydantic provides a set of skills and plugins for working with Logfire at
[github.com/pydantic/skills](https://github.com/pydantic/skills).

## What's included

The [pydantic/skills](https://github.com/pydantic/skills) repository includes:

- **Logfire plugin** — a Claude Code [plugin](https://code.claude.com/docs/en/plugins) that bundles
  skills, commands, and an MCP server for adding Logfire observability to your applications. Supports
  Python, JavaScript/TypeScript, and Rust with auto-instrumentation for frameworks like FastAPI,
  httpx, asyncpg, and more.
- **Standalone skills** — individual skills like `logfire-instrumentation` that can be installed
  separately.

## Installation

Skills and plugins are managed using the [`skills` CLI](https://github.com/vercel-labs/skills).

Install the Pydantic skills with:

```bash
npx skills install pydantic/skills
```

This will make the skills and plugins available in your Claude Code sessions.

## Usage

Once installed, Claude will automatically use the relevant skills when appropriate. You can also
invoke them directly using the `/` command:

```
/instrumentation
```

For more details on how skills work, see the
[Claude Code skills documentation](https://code.claude.com/docs/en/skills).
