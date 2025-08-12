import argparse
from logfire._internal.client import LogfireClient as LogfireClient

def parse_prompt(args: argparse.Namespace) -> None:
    """Creates a prompt to be used with your favorite LLM.

    The prompt assumes you are using Logfire MCP.
    """
