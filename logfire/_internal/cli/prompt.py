"""Prompt command for Logfire CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from logfire._internal.cli.auth import parse_auth
from logfire._internal.client import LogfireClient
from logfire._internal.utils import read_toml_file
from logfire.exceptions import LogfireConfigError

LOGFIRE_MCP_TOML = """
[mcp_servers.logfire]
url = "{url}"
"""


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

    if args.claude:
        configure_claude(client, console, update=update)
    elif args.codex:
        configure_codex(client, console, update=update)
    elif args.opencode:
        configure_opencode(client, console, update=update)

    response = client.get_prompt(args.organization, args.project, args.issue)
    sys.stdout.write(response['prompt'])


def _logfire_mcp_url(client: LogfireClient) -> str:
    return f'{client.base_url.rstrip("/")}/mcp'


def configure_claude(client: LogfireClient, console: Console, update: bool = False) -> None:
    if not shutil.which('claude'):
        console.print('claude is not installed. Install `claude`, or remove the `--claude` flag.')
        exit(1)

    output = subprocess.check_output(['claude', 'mcp', 'list']).decode('utf-8')
    already_configured = bool(re.search(r'(?m)^logfire[\s:]', output))

    if already_configured and not update:
        return

    if already_configured:
        subprocess.check_output(shlex.split('claude mcp remove logfire'))

    url = _logfire_mcp_url(client)
    subprocess.check_output(shlex.split(f'claude mcp add --transport http logfire {url}'))
    console.print(f'Logfire MCP server {"updated in" if already_configured else "added to"} Claude.', style='green')


def configure_codex(client: LogfireClient, console: Console, update: bool = False) -> None:
    if not shutil.which('codex'):
        console.print('codex is not installed. Install `codex`, or remove the `--codex` flag.')
        exit(1)

    codex_home = Path(os.getenv('CODEX_HOME', Path.home() / '.codex'))
    codex_config = codex_home / 'config.toml'
    if not codex_config.exists():
        console.print('Codex config file not found. Install `codex`, or remove the `--codex` flag.')
        exit(1)

    try:
        codex_config_data = read_toml_file(codex_config)
    except ValueError:
        console.print(f'Failed to parse {codex_config} as TOML. Please fix the file or update it manually.')
        exit(1)
    already_configured = 'logfire' in codex_config_data.get('mcp_servers', {})

    if already_configured and not update:
        return

    mcp_server_toml = LOGFIRE_MCP_TOML.format(url=_logfire_mcp_url(client))
    codex_config_content = codex_config.read_text()

    if already_configured:
        new_content = re.sub(
            r'\n?\[mcp_servers\.logfire\].*?(?=\n\[|\Z)',
            mcp_server_toml,
            codex_config_content,
            count=1,
            flags=re.DOTALL,
        )
        codex_config.write_text(new_content)
        console.print('Logfire MCP server updated in Codex.', style='green')
    else:
        codex_config.write_text(codex_config_content + mcp_server_toml)
        console.print('Logfire MCP server added to Codex.', style='green')


def configure_opencode(client: LogfireClient, console: Console, update: bool = False) -> None:
    if not shutil.which('opencode'):
        console.print('opencode is not installed. Install `opencode`, or remove the `--opencode` flag.')
        exit(1)

    try:
        output = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'])
    except subprocess.CalledProcessError:
        root_dir = Path.cwd()
    else:
        root_dir = Path(output.decode('utf-8').strip())

    opencode_config = root_dir / 'opencode.jsonc'
    opencode_config.touch()

    opencode_config_content = opencode_config.read_text()
    if opencode_config_content.strip():
        try:
            opencode_config_json: dict[str, Any] = json.loads(opencode_config_content)
        except json.JSONDecodeError:
            console.print(
                f'Failed to parse {opencode_config} as JSON. '
                'If it contains JSONC syntax (comments or trailing commas), please update it manually.'
            )
            exit(1)
    else:
        opencode_config_json = {}
    already_configured = 'logfire-mcp' in opencode_config_json.get('mcp', {})

    if already_configured and not update:
        return

    mcp_entry = opencode_mcp_json(_logfire_mcp_url(client))
    opencode_config_json.setdefault('mcp', {})['logfire-mcp'] = mcp_entry
    opencode_config.write_text(json.dumps(opencode_config_json, indent=2))
    console.print(f'Logfire MCP server {"updated in" if already_configured else "added to"} OpenCode.', style='green')


# https://opencode.ai/docs/mcp-servers/#remote
def opencode_mcp_json(url: str) -> dict[str, Any]:
    return {
        'type': 'remote',
        'url': url,
    }
