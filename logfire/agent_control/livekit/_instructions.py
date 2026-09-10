"""Where a LiveKit agent's prompt has seams, and how to put a managed one back together.

LiveKit gives an agent one prompt: `Agent(instructions=...)` is either a `str` or an `Instructions`
with up to three keyed variants, and the framework renders whichever the turn's modality asks for
into a single system message. Neither shape is a keyed list, so the ids this module synthesizes are
the whole reason the Logfire editor can offer per-block overrides rather than one giant textarea.

The ids ride on the prompt object itself -- `instruction_blocks(...)` returns an `Instructions` that
remembers what it was assembled from -- rather than on the control, so the seams belong to the text
being sent and travel with it wherever the agent is constructed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from livekit.agents.llm.chat_context import Instructions

from .. import Block

AGENT_BLOCK_ID = 'agent'
"""The id for the agent's own prompt -- the one id the contract reserves."""

MODALITY_BLOCK_IDS = frozenset({f'{AGENT_BLOCK_ID}:audio', f'{AGENT_BLOCK_ID}:text'})
"""The ids the modality variants are addressed under, which a declared block may not claim."""

SEPARATOR = '\n\n'
"""What LiveKit joins prompt parts with (`Instructions.render`), and so what a managed prompt does."""

Modality = Literal['audio', 'text']


def join(texts: Sequence[str]) -> str:
    """Join prompt parts the way `Instructions.render` does, empty ones dropped."""
    return SEPARATOR.join(text for text in texts if text)


class _BlockInstructions(Instructions):
    """An `Instructions` that remembers the ids its `common` text was assembled from.

    A subclass rather than a table kept next to the agent, because LiveKit hands this very object
    back on `Agent.instructions`: the seams are then readable from the prompt the agent is actually
    holding, and a prompt replaced at runtime by `update_instructions()` -- which stores a bare
    `str` -- loses them, which is exactly right, since the text they described is no longer what the
    agent says.
    """

    def __init__(self, blocks: Mapping[str, str], *, audio: str | None = None, text: str | None = None) -> None:
        super().__init__(join(list(blocks.values())), audio=audio, text=text)
        self.blocks = dict(blocks)
        """The declared blocks, by the id a published value addresses each one under."""


def instruction_blocks(blocks: Mapping[str, str], *, audio: str | None = None, text: str | None = None) -> Instructions:
    """The agent's prompt, split into the blocks Logfire offers separately.

    Pass the result to `Agent(instructions=...)`. The blocks are joined the way LiveKit joins prompt
    parts, so the agent sends exactly the prompt it would have sent as one string -- and each key
    becomes an id a published value can rewrite, remove, or add before, on its own.

    ```python
    from livekit.agents import Agent
    from logfire.agent_control.livekit import agent_control, instruction_blocks


    @agent_control(name='checkout_assistant')
    class CheckoutAgent(Agent):
        def __init__(self) -> None:
            super().__init__(
                instructions=instruction_blocks(
                    {
                        'agent': 'You are a concise checkout assistant.',
                        'refunds': 'Always confirm the order total before refunding.',
                    },
                    audio='Keep spoken answers to one sentence.',
                )
            )
    ```

    Args:
        blocks: The prompt's parts, in the order they are sent, keyed by the id each is addressed
            under. `'agent'` is the id the contract reserves for the agent's own prompt.
        audio: Extra instructions for spoken turns, addressed as `agent:audio`.
        text: Extra instructions for text turns, addressed as `agent:text`.

    Raises:
        ValueError: When `blocks` is empty. There is nothing to assemble, and a prompt passed
            straight to `Agent(instructions=...)` is already managed as one block keyed `agent`.
        ValueError: When a block claims `agent:audio` or `agent:text`. Those two ids belong to the
            variants below, and a block sharing one would be rewritten by every value published for
            the variant -- one override silently changing two parts of the prompt.
    """
    if not blocks:
        raise ValueError(
            '`instruction_blocks` needs at least one block to assemble, as '
            "`instruction_blocks({'agent': '...'})`; pass your prompt straight to "
            '`Agent(instructions=...)` to manage it as one block.'
        )
    if taken := MODALITY_BLOCK_IDS.intersection(blocks):
        raise ValueError(
            f'{", ".join(repr(id) for id in sorted(taken))} '
            f'{"is" if len(taken) == 1 else "are"} reserved for the `audio=` and `text=` variants; '
            'pass that text as `audio=` or `text=`, or give the block an id of its own.'
        )
    return _BlockInstructions(blocks, audio=audio, text=text)


def render(instructions: str | Instructions, modality: Modality) -> str:
    """The single string LiveKit sends for `instructions` on a turn of this modality."""
    return instructions.render(modality=modality) if isinstance(instructions, Instructions) else instructions


def blocks_for(instructions: str | Instructions, modality: Modality) -> list[Block]:
    """The blocks the agent is about to send, with the ids a published config addresses them by.

    Three sources of seams, in the order they are trusted:

    - the blocks `instruction_blocks()` assembled the prompt from, when that is still the object the
      agent is holding. `agent.update_instructions()` replaces the whole prompt at runtime with a
      bare string, and the declared seams describe text that is no longer being sent, so they go
      with it rather than staying pinned to something the agent no longer says;
    - `Instructions.common`, keyed `agent`, which is the id the contract reserves for "the agent's
      own prompt" -- and the id a plain `str` prompt gets too, so moving from one to the other does
      not orphan a published override;
    - the modality addition for this turn, keyed `agent:audio` or `agent:text`. It is a genuine
      LiveKit concept rather than a synthesized one, and only the turn's own variant is listed:
      the other is not part of this request, so a published value for it has nothing to reach.

    Every block is static. LiveKit has no per-request instruction callable -- a prompt that varies
    per turn is written by calling `update_instructions()`, which is invisible from here except as
    the lost seams above -- so nothing here is ever marked `dynamic`.
    """
    if isinstance(instructions, Instructions):
        common, addition = instructions.common, instructions.audio if modality == 'audio' else instructions.text
        declared = instructions.blocks if isinstance(instructions, _BlockInstructions) else None
    else:
        common, addition, declared = instructions, None, None

    if declared:
        blocks = [Block(text, id=id) for id, text in declared.items()]
    else:
        blocks = [Block(common, id=AGENT_BLOCK_ID)]
    if addition:
        blocks.append(Block(addition, id=f'{AGENT_BLOCK_ID}:{modality}'))
    return blocks


def baseline_blocks(instructions: str | Instructions) -> list[Block]:
    """Every block the agent can send, for the baseline the Logfire editor opens on.

    Unlike a request, the baseline lists both modality variants: a request carries one of them and a
    published value for the other would have nothing to reach, but the editor is describing the agent
    rather than one turn, and an `agent:text` block someone can only edit during a text call would be
    an odd thing to hide.
    """
    blocks = blocks_for(instructions, 'audio')
    if isinstance(instructions, Instructions) and instructions.text:
        blocks.append(Block(instructions.text, id=f'{AGENT_BLOCK_ID}:text'))
    return blocks
