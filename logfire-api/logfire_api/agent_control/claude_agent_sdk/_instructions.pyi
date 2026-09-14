from claude_agent_sdk import AgentDefinition as AgentDefinition, ClaudeAgentOptions
from claude_agent_sdk.types import SystemPromptFile, SystemPromptPreset
from collections.abc import Sequence
from logfire.agent_control import Block as Block
from typing import Any, TypeAlias

SYSTEM_ID: str
PRESET_ID: str
APPEND_ID: str
FILE_ID: str
AGENT_PREFIX: str
SystemPrompt: TypeAlias = str | SystemPromptPreset | SystemPromptFile | None

def instruction_blocks(options: ClaudeAgentOptions) -> list[Block]:
    '''Every prompt `options` states, in the order the agent sends them.

    Two of them are dynamic, which in this SDK means "the text is never in this process": Claude
    Code\'s preset prompt is assembled inside the CLI from the working directory, git status, and
    memory files, and a `system_prompt` file is read by the CLI at session start. Both are published
    as blocks that exist without text, so the Logfire editor shows the prompt is there and offers no
    override for it -- and the core refuses one anyway.

    `system_prompt=None` states no prompt at all (the CLI\'s minimal built-in one), so it contributes
    no block; instructions published for it are added rather than replacing anything.
    '''
def apply_instruction_blocks(options: ClaudeAgentOptions, blocks: Sequence[Block]) -> tuple[dict[str, Any], list[str]]:
    """Write applied blocks back into the fields they came from, as `ClaudeAgentOptions` changes.

    `blocks` is what `apply_instructions` returned, so an id that is missing was dropped and a block
    with no id was added. Added text is routed by its sink rather than by its position in the list:
    every added block goes into the agent's own system prompt -- appended to a custom string, or into
    a preset's `append` -- which is the only place this SDK has to put it.

    A subagent's block cannot be dropped at all, and the attempt is reported. Removing an instruction
    block removes *text*, and a subagent is not text: it has a description the model routes on, a
    tool list, and a model of its own. The CLI declares a subagent by its prompt and leaves one whose
    prompt is empty out of the session entirely -- so emptying it, the way `''` empties the agent's
    own `system_prompt`, would take the whole subagent away, which is not something a section that
    only describes instructions may do.

    Returns the changes to apply and any messages the caller should report under `on_unmatched`, for
    published text this agent's prompt shape has nowhere to put.
    """
