from _typeshed import Incomplete
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import EffortLevel as EffortLevel
from logfire.agent_control import to_milliseconds as to_milliseconds
from typing import Any

SUPPORTED_SETTINGS: Incomplete
MAX_OUTPUT_TOKENS_ENV: str
TIMEOUT_ENV: str
ANTHROPIC_PROVIDER: str

def baseline_model(options: ClaudeAgentOptions) -> str | None:
    """The code-defined model as a canonical `provider:model` string.

    Every model this SDK can name is an Anthropic one -- a model id or an alias like `sonnet` -- since
    Bedrock, Vertex, and the rest are selected by environment variables on the CLI subprocess rather
    than by the model string. So the provider is always `anthropic`, and a `None` model (the CLI's own
    default, chosen from settings or `ANTHROPIC_MODEL`) is not knowable from here at all.
    """
def managed_model(model: str) -> tuple[str | None, str | None]:
    """Lower a published `provider:model` string to what `ClaudeAgentOptions.model` takes.

    Returns the model to set and, when there is none, the reason to report. A string with no provider
    is passed through untouched so a framework-native id keeps working, and any provider other than
    `anthropic` is refused rather than silently truncated: this SDK's provider is a property of the
    environment the CLI runs in, not of the model string, so applying the model half of
    `bedrock:claude-fable-5-1` would send an Anthropic request under a name meant for Bedrock.
    """
def baseline_settings(options: ClaudeAgentOptions) -> dict[str, Any]:
    """The canonical settings `options` states, for the baseline the Logfire editor diffs against."""
def apply_managed_settings(options: ClaudeAgentOptions, patch: dict[str, Any]) -> dict[str, Any]:
    """Lower a settings patch to `ClaudeAgentOptions` changes.

    `patch` is what `apply_settings(config, supported=SUPPORTED_SETTINGS)` returned, so every key here
    is one this framework has a knob for. A published `thinking` sets both `thinking` and `effort`
    together, since the two are one statement in the contract and leaving the code's half in place is
    how you get `effort='high'` on an agent whose thinking a published value just turned off.
    """
