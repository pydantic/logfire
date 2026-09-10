"""The agent's one system message, read as addressable blocks and written back the way it came in.

LangChain has exactly one place instructions live: the `SystemMessage` that `create_agent` puts in
front of every request. It has no named sections, so the only seam a published config can address is
the one the message itself offers -- a `content` list of text blocks, each of which may carry an
`id`. This module is that translation, in both directions.

An `id` is also the only *provenance* there is. A middleware runs before this one and can replace the
whole system message -- that is what `@dynamic_prompt` is for -- and by the time a `ModelRequest`
arrives here, text the agent was written with and text a middleware computed from this run's tenant,
user, or retrieved documents are the same string with nothing to tell them apart. So an `id` the code author
wrote is read as their declaration that the block is theirs and stays put: those blocks are static,
published with their text, and addressable. An `id` *LangChain* generated is not that declaration --
see `GENERATED_BLOCK_ID` -- and is read as a seam like anything else. Everything else is a dynamic seam -- published as an id
and a `dynamic` flag with no text, and refused as an override target -- because publishing one
request's rendering puts one run's data in a variable the whole Logfire project can read, and an
override on it would pin that rendering forever.

The other way to declare a block is to hand the middleware the prompt itself, as a mapping of id to
text: an assembled prompt is code-side by construction, because this module is what built it. That is
`assemble_system_prompt`, and it is the same two kinds of block -- a string is static, a callable is
recomputed per request and is therefore a seam.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import SystemMessage

from logfire.agent_control import Block

Instruction: TypeAlias = str | Callable[[ModelRequest[Any]], str]
"""One declared instruction block: fixed text, or text this request works out for itself.

A callable is handed the `ModelRequest` -- and through it the run's state and runtime context -- and
is called on every request, which is what makes it a seam rather than something a published value may
replace. A string is the block as written, and is both published and editable.
"""

GENERATED_BLOCK_ID = re.compile(r'lc_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z')
"""LangChain's own block id: `lc_` and a UUID4, which `create_text_block()` and friends generate.

Read as *not* a declaration, which is the whole point of the rule this file is built on. A middleware
that assembles this request's system prompt with LangChain's own helpers gets one of these per block
per request, and taking it for the code author saying "this block is mine" would do both of the
things the contract forbids: publish that request's text -- this tenant, this user, this run's
retrieved documents -- into a variable every member of the project can read, and offer it for
override under an id no later request will ever carry again.

Matched exactly rather than by prefix, so a block someone deliberately called `lc_role` is still
theirs.
"""

SYSTEM_BLOCK_ID = 'system'
"""The id of a plain-string system prompt: the agent's prompt as written, one block.

The contract reserves `'agent'` for that, but LangChain users see this as `system_prompt=` on
`create_agent` and as `system_message` on a `ModelRequest`, so the id is spelled the way the
framework spells it. Blocks of a `content` list are `system:<id>`, or `system:<index>` for a block
with no `id` of its own.
"""


@dataclass(frozen=True)
class _Slot:
    """One entry of the system message's content, and the block it offers to a published config."""

    entry: str | dict[str, Any]
    """The entry exactly as the agent wrote it, which is what carries `cache_control` and the rest."""
    block: Block | None = None
    """The addressable text, or `None` for an entry that is not text and cannot be edited."""


def _with_text(entry: str | dict[str, Any], text: str) -> str | dict[str, Any]:
    """The entry as it came in, saying something else, without the `id` that is ours and not a provider's."""
    if isinstance(entry, str):
        return text
    return {key: value for key, value in entry.items() if key != 'id'} | {'text': text}


@dataclass(frozen=True)
class SystemPrompt:
    """A `SystemMessage` split into the blocks a published `instructions` section can address.

    Kept as a pair -- the blocks, and the entries they came out of -- because writing the section
    back is not "join the text": an entry carries the provider directives the agent put on it
    (Anthropic's `cache_control` above all), and replacing a list of annotated blocks with a bare
    string would throw away the user's own cache breakpoints on every request.
    """

    slots: tuple[_Slot, ...]
    plain: bool
    """Whether the content came in as a bare string rather than a list of blocks.

    Written back the way it arrived, both directions. A string prompt rendered as a one-element list
    is a different payload to every provider -- and, on the ones that cache, a different prefix --
    which is not something managing an agent's instructions should quietly do to it.
    """

    message: SystemMessage | None = None
    """The message the blocks were read out of, for everything about it that is not its content.

    A `SystemMessage` is more than the text it carries: it has a `name`, an `id`, and the
    `additional_kwargs` an integration reads message-level provider directives out of. Rendering
    replaces the content of the message that came in rather than building a new one, because a
    prompt whose blocks carry `id`s is re-rendered on *every* request -- to strip those ids -- so a
    fresh message would drop all of that on a request nobody published anything for.
    """

    assembled: bool = False
    """Whether this prompt is the middleware's own assembly rather than the request's own message.

    Two things follow from it, and both are the point of declaring instructions there: the blocks are
    code-side because this module built them out of what the code passed, and the prompt is not on the
    request yet, so it is rendered onto every request rather than only when something changed it.
    """

    @property
    def blocks(self) -> list[Block]:
        """The addressable blocks, in the order the model is shown them."""
        return [slot.block for slot in self.slots if slot.block is not None]

    @property
    def carries_ids(self) -> bool:
        """Whether any entry names itself with an `id`, which is not ours to forward to a provider.

        An `id` on a text block is a LangChain-side label. Anthropic drops it on the way out, but
        OpenAI forwards content blocks verbatim, so a prompt annotated for Agent Control would start
        sending an unknown field to the API. Rendering strips them, and this is what says the prompt
        needs rendering even when nothing is published.
        """
        return any(isinstance(slot.entry, dict) and 'id' in slot.entry for slot in self.slots)

    @property
    def must_render(self) -> bool:
        """Whether the request needs a new system message even when nothing was published."""
        return self.assembled or self.carries_ids

    def render(self, blocks: Sequence[Block]) -> SystemMessage | None:
        """The system message to send, given the blocks a published config left behind.

        The blocks are the order to send, and the slots are what to send: each block is matched back
        to the entry it came from, so an entry keeps everything about itself except the text, while a
        block the config added has no entry of its own and becomes a plain text one where
        `apply_instructions` placed it -- ahead of the first block whose text this adapter cannot
        attribute to the code, which is where the contract keeps managed text so a provider can still
        cache the prefix. A block the config removed drops its entry, and an entry that is not text
        keeps its place among the ones that are.

        A config that removed everything leaves no system message at all rather than an empty one,
        which is what `create_agent` sends for an agent written without a `system_prompt`.
        """
        if self.plain:
            texts = [block.text for block in blocks]
            return self._message('\n\n'.join(texts)) if texts else None
        entries: list[str | dict[str, Any]] = []
        position = 0
        for block in blocks:
            if block.id is None:
                entries.append({'type': 'text', 'text': block.text})
                continue
            # Everything the agent wrote before this block: an entry that is not text is carried
            # through, and a text entry that is not in `blocks` is one the config removed.
            while (slot := self.slots[position]).block is None or slot.block.id != block.id:
                if slot.block is None:
                    entries.append(slot.entry)
                position += 1
            entries.append(_with_text(slot.entry, block.text))
            position += 1
        entries.extend(slot.entry for slot in self.slots[position:] if slot.block is None)
        return self._message(entries) if entries else None

    def _message(self, content: str | list[str | dict[str, Any]]) -> SystemMessage:
        """The message to send: the one that came in, saying something else, or a new one."""
        if self.message is None:
            return SystemMessage(content=content)
        return self.message.model_copy(update={'content': content})


def read_system_prompt(message: SystemMessage | None) -> SystemPrompt:
    """Split the system message this request is about to send into addressable blocks.

    A bare string is the agent's whole prompt and gets the one reserved id. A content list gives one
    block per text entry, keyed by the entry's own `id` when it has one -- which is the only stable
    key there is, since an index moves the moment someone inserts a paragraph. Anything that is not
    text is carried through untouched and offered to nobody.

    A block is static only when the entry names itself with an `id`. Nothing else here is evidence of
    where the text came from: a middleware ahead of this one hands over a `SystemMessage` it built
    from the run's own input exactly the way `create_agent` hands over the one from the code, so a
    block nobody labelled is a seam whose rendering belongs to the request rather than to the agent.
    """
    if message is None:
        # An agent written without a `system_prompt` is a prompt of no blocks, and a published block
        # added to it is one string, which is what `create_agent` would have made of it in code.
        return SystemPrompt(slots=(), plain=True)
    content = message.content
    if isinstance(content, str):
        return SystemPrompt(
            slots=(_Slot(content, Block(text=content, id=SYSTEM_BLOCK_ID, dynamic=True)),), plain=True, message=message
        )
    slots: list[_Slot] = []
    for index, entry in enumerate(content):
        if isinstance(entry, str):
            slots.append(_Slot(entry, Block(text=entry, id=f'{SYSTEM_BLOCK_ID}:{index}', dynamic=True)))
            continue
        text = entry.get('text')
        if entry.get('type') != 'text' or not isinstance(text, str):
            slots.append(_Slot(entry))
            continue
        key = entry.get('id')
        declared = isinstance(key, str) and bool(key) and not GENERATED_BLOCK_ID.fullmatch(key)
        block_id = f'{SYSTEM_BLOCK_ID}:{key if declared else index}'
        slots.append(_Slot(entry, Block(text=text, id=block_id, dynamic=not declared)))
    return SystemPrompt(slots=tuple(slots), plain=False, message=message)


def assemble_system_prompt(instructions: Mapping[str, Instruction], request: ModelRequest[Any]) -> SystemPrompt:
    """The prompt the middleware was given, as the blocks a published config can address.

    Declared rather than read, which is the whole difference: these blocks came from the code through
    an argument, so their text is the agent as written and can be published and edited, while a
    prompt found on a request is text this adapter cannot attribute to anything.

    Fixed blocks are sent first, in the order they were declared, and computed ones after them, so a
    block that changes per request never moves the prefix a provider can cache -- which is also where
    `apply_instructions` puts a block a published config adds.
    """
    static: list[_Slot] = []
    dynamic: list[_Slot] = []
    for key, instruction in instructions.items():
        block_id = f'{SYSTEM_BLOCK_ID}:{key}'
        if callable(instruction):
            text = instruction(request)
            dynamic.append(_Slot(text, Block(text=text, id=block_id, dynamic=True)))
        else:
            static.append(_Slot(instruction, Block(text=instruction, id=block_id, dynamic=False)))
    # One string, because that is what the code would have passed `create_agent` had it written the
    # prompt out by hand, and a one-element content list is a different payload to every provider.
    return SystemPrompt(slots=(*static, *dynamic), plain=True, assembled=True)
