from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import SystemMessage
from logfire.agent_control import Block as Block
from typing import Any, TypeAlias

Instruction: TypeAlias = str | Callable[[ModelRequest[Any]], str]
SYSTEM_BLOCK_ID: str

@dataclass(frozen=True)
class _Slot:
    """One entry of the system message's content, and the block it offers to a published config."""
    entry: str | dict[str, Any]
    block: Block | None = ...

@dataclass(frozen=True)
class SystemPrompt:
    '''A `SystemMessage` split into the blocks a published `instructions` section can address.

    Kept as a pair -- the blocks, and the entries they came out of -- because writing the section
    back is not "join the text": an entry carries the provider directives the agent put on it
    (Anthropic\'s `cache_control` above all), and replacing a list of annotated blocks with a bare
    string would throw away the user\'s own cache breakpoints on every request.
    '''
    slots: tuple[_Slot, ...]
    plain: bool
    message: SystemMessage | None = ...
    assembled: bool = ...
    @property
    def blocks(self) -> list[Block]:
        """The addressable blocks, in the order the model is shown them."""
    @property
    def carries_ids(self) -> bool:
        """Whether any entry names itself with an `id`, which is not ours to forward to a provider.

        An `id` on a text block is a LangChain-side label. Anthropic drops it on the way out, but
        OpenAI forwards content blocks verbatim, so a prompt annotated for Agent Control would start
        sending an unknown field to the API. Rendering strips them, and this is what says the prompt
        needs rendering even when nothing is published.
        """
    @property
    def must_render(self) -> bool:
        """Whether the request needs a new system message even when nothing was published."""
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
def assemble_system_prompt(instructions: Mapping[str, Instruction], request: ModelRequest[Any]) -> SystemPrompt:
    """The prompt the middleware was given, as the blocks a published config can address.

    Declared rather than read, which is the whole difference: these blocks came from the code through
    an argument, so their text is the agent as written and can be published and edited, while a
    prompt found on a request is text this adapter cannot attribute to anything.

    Fixed blocks are sent first, in the order they were declared, and computed ones after them, so a
    block that changes per request never moves the prefix a provider can cache -- which is also where
    `apply_instructions` puts a block a published config adds.
    """
