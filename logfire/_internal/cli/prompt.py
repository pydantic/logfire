"""Prompt command for Logfire CLI."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from logfire._internal.cli.ai_tools import AiToolIntegration, resolve_ai_tool
from logfire._internal.cli.auth import parse_auth
from logfire._internal.client import LogfireClient
from logfire.exceptions import LogfireConfigError


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

    integration = _selected_mcp_integration(args)
    if integration is not None:
        integration.configure_mcp_server(mcp_url=_logfire_mcp_url(client), console=console, update=update)

    if not getattr(args, 'project', None):
        if integration is not None:
            return
        console.print('The --project option is required unless configuring an agent integration.')
        sys.exit(1)

    response = client.get_prompt(args.organization, args.project, args.issue)
    sys.stdout.write(response['prompt'])


def _logfire_mcp_url(client: LogfireClient) -> str:
    return f'{client.base_url.rstrip("/")}/mcp'


def _selected_mcp_integration(args: argparse.Namespace) -> AiToolIntegration | None:
    for name in ('claude', 'codex', 'opencode'):
        if getattr(args, name):
            return resolve_ai_tool(name)
    return None
