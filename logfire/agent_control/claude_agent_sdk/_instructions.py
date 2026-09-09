"""Every prompt a `ClaudeAgentOptions` states, as addressable blocks, and back again.

The SDK has no list of prompt blocks: it has one `system_prompt` (a string, a preset with an
`append`, or a file) and one prompt per subagent in `agents`. Those seams are what an editor can
offer overrides for, so each gets an id here, and a published value is written back to the field it
came from.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, TypeAlias

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions
from claude_agent_sdk.types import SystemPromptFile, SystemPromptPreset

from logfire.agent_control import Block

SYSTEM_ID = 'system'
"""`system_prompt` as a plain string: the agent's own prompt, whole."""

PRESET_ID = 'preset:claude_code'
"""Claude Code's built-in system prompt, which the CLI renders and never shows the SDK."""

APPEND_ID = 'append'
"""The text a preset system prompt appends after Claude Code's own."""

FILE_ID = 'system:file'
"""A `system_prompt` read from a file by the CLI, whose contents the SDK never sees."""

AGENT_PREFIX = 'agent:'
"""Prefix for one subagent's prompt: `agent:<key>` for each key in `agents`."""

_SEPARATOR = '\n\n'
"""What blocks written into one prompt field are joined with, matching how the CLI joins its own."""


SystemPrompt: TypeAlias = str | SystemPromptPreset | SystemPromptFile | None
"""Every shape `ClaudeAgentOptions.system_prompt` takes; `None` is the CLI's own minimal prompt."""


def _preset(system_prompt: SystemPrompt) -> SystemPromptPreset | None:
    if isinstance(system_prompt, dict) and system_prompt.get('type') == 'preset':
        preset: SystemPromptPreset = system_prompt  # type: ignore[assignment]
        return preset
    return None


def _file(system_prompt: SystemPrompt) -> SystemPromptFile | None:
    if isinstance(system_prompt, dict) and system_prompt.get('type') == 'file':
        file: SystemPromptFile = system_prompt  # type: ignore[assignment]
        return file
    return None


def instruction_blocks(options: ClaudeAgentOptions) -> list[Block]:
    """Every prompt `options` states, in the order the agent sends them.

    Two of them are dynamic, which in this SDK means "the text is never in this process": Claude
    Code's preset prompt is assembled inside the CLI from the working directory, git status, and
    memory files, and a `system_prompt` file is read by the CLI at session start. Both are published
    as blocks that exist without text, so the Logfire editor shows the prompt is there and offers no
    override for it -- and the core refuses one anyway.

    `system_prompt=None` states no prompt at all (the CLI's minimal built-in one), so it contributes
    no block; instructions published for it are added rather than replacing anything.
    """
    blocks: list[Block] = []
    system_prompt = options.system_prompt
    preset = _preset(system_prompt)
    if isinstance(system_prompt, str):
        blocks.append(Block(system_prompt, id=SYSTEM_ID))
    elif preset is not None:
        blocks.append(Block('', id=PRESET_ID, dynamic=True))
        append = preset.get('append')
        if append is not None:
            blocks.append(Block(append, id=APPEND_ID))
    elif _file(system_prompt) is not None:
        blocks.append(Block('', id=FILE_ID, dynamic=True))
    for key, agent in (options.agents or {}).items():
        blocks.append(Block(agent.prompt, id=f'{AGENT_PREFIX}{key}'))
    return blocks


def _joined(texts: Sequence[str]) -> str:
    return _SEPARATOR.join(text for text in texts if text)


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
    by_id = {block.id: block for block in blocks if block.id is not None}
    added = [block.text for block in blocks if block.id is None]
    changes: dict[str, Any] = {}
    unapplied: list[str] = []

    system_prompt = options.system_prompt
    preset = _preset(system_prompt)
    file = _file(system_prompt)
    if isinstance(system_prompt, str):
        block = by_id.get(SYSTEM_ID)
        # A dropped prompt becomes `''`, which is what the SDK already sends for "no custom prompt".
        changes['system_prompt'] = _joined([block.text if block is not None else '', *added])
    elif preset is not None:
        block = by_id.get(APPEND_ID)
        append = _joined([block.text if block is not None else '', *added])
        rewritten: dict[str, Any] = {key: value for key, value in preset.items() if key != 'append'}
        if append:
            rewritten['append'] = append
        changes['system_prompt'] = rewritten
    elif file is not None:
        if added:
            # The prompt lives in a file the CLI reads; there is nothing in the options to append to,
            # and rewriting the user's file is not this adapter's to do.
            unapplied.append(
                f'Managed agent config adds instructions, but this agent reads its system prompt from '
                f'the file {file["path"]!r}; the Claude Agent SDK has no way to add to a system prompt '
                'it never sees, so those blocks are not applied.'
            )
    elif added:
        changes['system_prompt'] = _joined(added)

    agents = options.agents
    if agents:
        managed: dict[str, AgentDefinition] = {}
        for key, agent in agents.items():
            block = by_id.get(f'{AGENT_PREFIX}{key}')
            if block is None:
                # The published value removed this block. The CLI declares a subagent *by* its
                # prompt: one whose prompt is empty is missing from the session's agent list
                # entirely, so applying the removal would take away the subagent, its description,
                # and its tools -- which is not something a section that only describes text may do.
                unapplied.append(
                    f'Managed agent config removes instruction block {AGENT_PREFIX + key!r}, but the `claude` CLI '
                    f'drops a subagent whose prompt is empty, so removing that block would take the subagent '
                    f'{key!r} out of the session along with its description and its tool list. That subagent keeps '
                    'the prompt this agent was written with; publish text for the block to change it instead.'
                )
                managed[key] = agent
                continue
            managed[key] = agent if block.text == agent.prompt else replace(agent, prompt=block.text)
        changes['agents'] = managed

    return changes, unapplied
