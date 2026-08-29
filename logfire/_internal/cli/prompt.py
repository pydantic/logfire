"""Prompt command for Logfire CLI."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from logfire._internal.cli.ai_tools import mcp_ai_tool_names, resolve_ai_tool
from logfire._internal.cli.auth import parse_auth
from logfire._internal.client import LogfireClient
from logfire.exceptions import LogfireConfigError

# Derived from the integration registry so a tool that gains MCP support does not also have to be
# added here, and so the `--<tool>` flags always match the tools that can actually be configured.
PROMPT_AI_TOOLS = mcp_ai_tool_names()


def parse_prompt(args: argparse.Namespace) -> None:
    """Creates a prompt to be used with your favorite LLM.

    The prompt assumes you are using Logfire MCP.
    """
    console = Console(file=sys.stderr)

    try:
        client = LogfireClient.from_url(args.logfire_url)
    except LogfireConfigError:  # pragma: no cover
        parse_auth(args)
        client = LogfireClient.from_url(args.logfire_url)

    update = bool(getattr(args, 'update', False))

    configured_tool = next((tool for tool in PROMPT_AI_TOOLS if getattr(args, tool, False)), None)
    if configured_tool:
        resolve_ai_tool(configured_tool).configure_mcp_server(
            mcp_url=_logfire_mcp_url(client), console=console, update=update
        )

    if not getattr(args, 'project', None):
        if configured_tool:
            return
        console.print('The --project option is required unless configuring an agent integration.')
        sys.exit(1)

    response = client.get_prompt(args.organization, args.project, args.issue)
    sys.stdout.write(response['prompt'])


def _logfire_mcp_url(client: LogfireClient) -> str:
    return f'{client.base_url.rstrip("/")}/mcp'
