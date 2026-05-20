import argparse
from _typeshed import Incomplete
from logfire._internal.cli.ai_tools import resolve_ai_tool as resolve_ai_tool
from logfire._internal.cli.auth import parse_auth as parse_auth
from logfire._internal.client import LogfireClient as LogfireClient
from logfire.exceptions import LogfireConfigError as LogfireConfigError

PROMPT_AI_TOOLS: Incomplete

def parse_prompt(args: argparse.Namespace) -> None:
    """Creates a prompt to be used with your favorite LLM.

    The prompt assumes you are using Logfire MCP.
    """
