"""Prompt command for Logfire CLI."""

from __future__ import annotations

import argparse
import sys

from logfire._internal.client import LogfireClient
from logfire.exceptions import LogfireConfigError


def parse_prompt(args: argparse.Namespace) -> None:
    """Creates a prompt to be used with your favorite LLM.

    The prompt assumes you are using Logfire MCP.
    """
    try:
        organization, project = args.project.split('/')
    except ValueError:
        raise LogfireConfigError('Project must be in the format <org>/<project>')

    client = LogfireClient.from_url(args.logfire_url)

    response = client.get_prompt(organization, project, args.issue)
    sys.stdout.write(response['prompt'])
