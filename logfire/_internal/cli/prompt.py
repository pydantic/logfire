"""Prompt command for Logfire CLI."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from logfire._internal.client import LogfireClient
from logfire.exceptions import LogfireConfigError

LOGFIRE_MCP_TOML = """
[mcp_servers.logfire]
command = "uvx"
args = ["logfire-mcp@latest"]
env = {{ "LOGFIRE_READ_TOKEN": "{token}" }}
"""


def parse_prompt(args: argparse.Namespace) -> None:
    """Creates a prompt to be used with your favorite LLM.

    The prompt assumes you are using Logfire MCP.
    """
    console = Console(file=sys.stderr)

    try:
        client = LogfireClient.from_url(args.logfire_url)
    except LogfireConfigError as e:  # pragma: no cover
        console.print(e.args[0], style='red')
        return

    if args.claude:
        output = subprocess.check_output(['claude', 'mcp', 'list'])
        if 'logfire-mcp' not in output.decode('utf-8'):
            token = _create_read_token(client, args.organization, args.project, console)
            subprocess.check_output(
                shlex.split(f'claude mcp add logfire -e LOGFIRE_READ_TOKEN={token} -- uvx logfire-mcp@latest')
            )
            console.print('Logfire MCP server added to Claude.', style='green')
    elif args.codex:
        codex_home = Path(os.getenv('CODEX_HOME', Path.home() / '.codex'))
        codex_config = codex_home / 'config.toml'
        if not codex_config.exists():
            console.print('Codex config file not found. Install `codex`, or remove the `--codex` flag.')
            return

        codex_config_content = codex_config.read_text()

        if 'logfire-mcp' not in codex_config_content:
            token = _create_read_token(client, args.organization, args.project, console)
            mcp_server_toml = LOGFIRE_MCP_TOML.format(token=token)
            codex_config.write_text(codex_config_content + mcp_server_toml)
            console.print('Logfire MCP server added to Codex.', style='green')

    response = client.get_prompt(args.organization, args.project, args.issue)
    sys.stdout.write(response['prompt'])


def _create_read_token(client: LogfireClient, organization: str, project: str, console: Console) -> str:
    console.print('Logfire MCP server not found. Creating a read token...', style='yellow')
    response = client.create_read_token(organization, project)
    return response['token']
