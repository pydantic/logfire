"""Prompt command for Logfire CLI."""

from __future__ import annotations

import argparse
import sys

from logfire._internal.client import LogfireClient


def parse_prompt(args: argparse.Namespace) -> None:
    """Creates a prompt to be used with your favorite LLM.

    The prompt assumes you are using Logfire MCP.
    """
    client = LogfireClient.from_url(args.logfire_url)
    response = client.get_prompt(args.organization, args.project, args.issue)
    sys.stdout.write(response['prompt'])
