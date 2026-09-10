from ._instructions import Instruction as Instruction, SystemPrompt as SystemPrompt, assemble_system_prompt as assemble_system_prompt, read_system_prompt as read_system_prompt
from ._models import build_model as build_model, read_model_id as read_model_id
from ._settings import carry_settings as carry_settings, lower_settings as lower_settings, read_settings as read_settings
from ._tools import apply_tools as apply_tools, read_tools as read_tools, rename_tool_calls as rename_tool_calls, rename_tool_choice as rename_tool_choice
from _typeshed import Incomplete
from collections.abc import Awaitable as Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse, ToolCallRequest
from langchain.agents.middleware.types import PrivateStateAttr as PrivateStateAttr
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.types import Command
from logfire import Logfire as Logfire
from logfire.agent_control import AgentConfig as AgentConfig, AgentControl as AgentControl, OnUnmatched as OnUnmatched, Resolution as Resolution, apply_instructions as apply_instructions, build_baseline as build_baseline, merge_settings as merge_settings
from typing import Annotated, Any
from typing_extensions import NotRequired

STATE_KEY: str
NAME_KEY: str
DEFAULT_AGENT_NAME: str

class AgentControlState(AgentState[Any]):
    """The agent state, plus the agent this run is of and the resolution it started from.

    The config lives in state rather than on the middleware because a middleware instance is shared
    by every concurrent run of its agent, and the whole point of resolving in `before_agent` is that
    one run applies one version of the config from its first model request to its last -- so every
    span of the run agrees on the version that produced it, and a publish mid-run takes effect on
    the next run rather than halfway through this one. Both are marked private so they stay out of
    the agent's input and output schemas: neither is something a caller passes in or reads back.

    The agent's *name* rides along for the same reason. It is read off the run, so two concurrent
    runs of one middleware can be of two differently named agents, and a name kept on the middleware
    would be whichever run wrote it last by the time a later node reads it -- which is how a request
    would come to publish one run's baseline under another run's variable.
    """
    logfire_agent_control: NotRequired[Annotated[Resolution, PrivateStateAttr]]
    logfire_agent_control_name: NotRequired[Annotated[str, PrivateStateAttr]]

@dataclass(frozen=True)
class _AppliedRequest:
    """One model request with the run's config applied, and how to read the reply it comes back with."""
    request: ModelRequest[Any]
    reverse: dict[str, str] = field(default_factory=dict[str, str])
    def in_code_names(self, response: ModelResponse[Any]) -> ModelResponse[Any]:
        """The reply, with every call to a renamed tool sent back to the tool the code defined.

        Done here, before the reply is returned to the model node, because everything downstream of
        this point is the user's side of the rename: `ToolNode` resolves a call by name against the
        tools the agent registered, a `wrap_tool_call` in any other middleware is keyed on the name
        the code gave the tool, and whatever the graph writes down -- state, a checkpoint, a trace --
        is what a later run is resumed from. A rename is a thing the model is told, and this is the
        boundary it stops at.
        """

class AgentControlMiddleware(AgentMiddleware[AgentControlState, Any, Any]):
    """Make a LangChain agent's instructions, model, settings, and tool descriptions editable in Logfire.

    [`agent_control`][logfire.agent_control.langchain.agent_control] is how you build one; this is
    the type it returns, for an annotation or a subclass. Add it to `create_agent(middleware=[...])`,
    **last**, and the agent keeps doing exactly what its code says until someone publishes a value in
    Logfire.

    Last, because `wrap_model_call` handlers compose first-in-list as the outermost layer: the last
    middleware is the innermost one, which is both the only position that sees the request every
    other middleware has finished assembling and the only one whose changes nothing downstream can
    overwrite.

    The agent's `name` is the config's key. It is read off each run, where `create_agent` puts the
    `name` it was given and where the LangChain instrumentation reads the name it puts on the agent's
    spans -- so the config lines up with the agent you are already looking at, including when a run's
    own `metadata` renames it, which renames it in both places for that run and no other. An agent
    built without a name has none to key on -- `create_agent` calls it `'LangGraph'` -- and that is
    an error rather than a guess. Pass `name=` here for a key no run can move.
    """
    state_schema = AgentControlState
    tools: Incomplete
    def __init__(self, *, name: str | None = None, instructions: Mapping[str, Instruction] | None = None, label: str | None = None, logfire_instance: Logfire | None = None, on_unmatched: OnUnmatched = 'warn', publish_baseline: bool = True) -> None:
        """Configure how this agent's managed config is read and published.

        Args:
            name: The agent's name, which its config is keyed on as the Logfire variable
                `agent__<name>`. Defaults to the `name` the run says the agent has, which is the one
                that already identifies it in Logfire; pass it here for a key no run can move.
            instructions: The agent's prompt, block by block, instead of `create_agent`'s
                `system_prompt`. Each key is the block's id and each value is its text, or a callable
                taking the `ModelRequest` for a block this request works out for itself. Declaring
                the prompt here is what makes its blocks code-side: they are published with their
                text and can be replaced or removed from Logfire one at a time, while text this
                middleware merely finds on a request cannot be told from a rendering of one run.
            label: The label to resolve, such as `'production'`. When `None`, the variable's own
                targeting rules and rollout choose which label this process gets.
            logfire_instance: The Logfire instance to resolve and publish through. Defaults to the
                global one that `logfire.configure()` sets up.
            on_unmatched: What to do about a published entry that reaches nothing in this
                deployment -- an instruction id this agent's prompt does not carry, an override
                naming a tool it does not advertise, a setting this model has no knob for.
                `'warn'` (the default) says so once per process, `'error'` fails the request, and
                `'ignore'` says nothing.
            publish_baseline: Whether to publish what the agent sends to Logfire, which is what the
                editor diffs published values against and what creates the variable the first time.
                Disable it when the Logfire token is intentionally read-only.
        """
    def before_agent(self, state: AgentControlState, runtime: Runtime[Any], config: RunnableConfig | None = None) -> dict[str, Any]:
        """Read the published config once, and carry it through every request of this run.

        The run's `config` is asked for by name, which is how LangGraph injects it into a node, and
        it is the only place a middleware can see what the agent is called: `create_agent` puts the
        `name` it was given on every run as `lc_agent_name`, the same value Logfire's LangChain
        instrumentation names the agent's spans with. The compiled graph is not handed to a
        middleware, and `langgraph.config.get_config()` is unavailable to a sync hook running under
        an async invocation on Python 3.10.
        """
    def wrap_model_call(self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]) -> ModelResponse[Any]:
        """Apply the run's config to the request the model is about to be sent."""
    async def awrap_model_call(self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]]) -> ModelResponse[Any]:
        """Apply the run's config to the request the model is about to be sent."""
    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]]) -> ToolMessage | Command[Any]:
        '''Run a tool call inside the version of the config that asked for it.

        The call itself is passed straight through: it already names the code\'s tool, because the
        model\'s reply was translated back before it ever reached the graph. Defining this hook is not
        only for the telemetry, though -- `create_agent` skips its "unknown client-side tool" check
        for an agent whose middleware wraps tool calls, which is what lets a request advertise a tool
        under a name `ToolNode` does not hold.
        '''
    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]) -> ToolMessage | Command[Any]:
        """Run a tool call inside the version of the config that asked for it."""

def agent_control(*, name: str | None = None, instructions: Mapping[str, Instruction] | None = None, label: str | None = None, on_unmatched: OnUnmatched = 'warn', publish_baseline: bool = True, logfire_instance: Logfire | None = None) -> AgentControlMiddleware:
    '''Make a LangChain agent configurable from Logfire, as one middleware to add **last**.

    ```python skip-run="true" skip-reason="external-connection"
    from langchain.agents import create_agent

    import logfire
    from logfire.agent_control.langchain import agent_control

    logfire.configure()

    agent = create_agent(
        \'anthropic:claude-haiku-4-5\',
        tools=[get_weather],
        name=\'checkout_assistant\',
        middleware=[
            agent_control(
                instructions={
                    \'role\': \'You are a concise checkout assistant.\',
                    \'refunds\': \'Always confirm the order total before refunding.\',
                },
                label=\'production\',
            )
        ],
    )
    ```

    The prompt moves from `create_agent(system_prompt=...)` into `instructions=`, and each block
    becomes one someone can rewrite or remove in Logfire on its own. A prompt kept on `create_agent`
    still works, and is still applied to -- but only the blocks of a `SystemMessage` content list
    that name themselves with an `id` are editable, because nothing else about a request says whether
    its text came from your code or from a middleware that computed it for this one run.

    Args:
        name: The agent\'s name, which its config is keyed on as the Logfire variable
            `agent__<name>`. Defaults to the `name` the run says the agent has, which is what
            already identifies it in Logfire; an agent created without one has no name to key on,
            and that is an error rather than a guess. Pass it here for a key no run can move.
        instructions: The agent\'s prompt, block by block, instead of `create_agent`\'s
            `system_prompt`. Each key is the block\'s id and each value is its text, or a callable
            taking the `ModelRequest` for a block this request works out for itself. Declaring the
            prompt here is what makes its blocks editable: they go into the baseline with their
            text and can be replaced or removed from Logfire one at a time, while a prompt this
            middleware merely finds on a request is a seam it cannot attribute to your code.
        label: The label to resolve, such as `\'production\'`. When `None`, the variable\'s own
            targeting rules and rollout choose which label this process gets.
        on_unmatched: What to do about a published entry that reaches nothing in this deployment.
            `\'warn\'` (the default) says so once per process, `\'error\'` fails the request, and
            `\'ignore\'` says nothing.
        publish_baseline: Whether to publish what the agent sends to Logfire, which is what the
            editor diffs published values against and what creates the variable the first time.
        logfire_instance: The Logfire instance to resolve and publish through. Defaults to the
            global one that `logfire.configure()` sets up.

    Returns:
        The middleware to put last in `create_agent(middleware=[...])`. It reads and applies the
        config; it never changes the agent, the model, or the tool objects you pass in.
    '''
