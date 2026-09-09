from .. import AgentControl, OnUnmatched, Resolution
from dataclasses import dataclass
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from logfire import Logfire

__all__ = ['agent_control']

def agent_control(agent: LlmAgent, *, name: str | None = None, label: str | None = None, on_unmatched: OnUnmatched = 'warn', publish_baseline: bool = True, logfire_instance: Logfire | None = None) -> LlmAgent:
    """Make an ADK agent's instructions, model, settings, and tool definitions editable from Logfire.

    The agent is wired up in place and returned -- the same object, not a copy -- so it can be
    wrapped where it is built:

    ```python
    agent = agent_control(
        LlmAgent(
            name='checkout_assistant',
            model='gemini-2.5-flash',
            instruction='You are a concise checkout assistant.',
        ),
        label='production',
    )
    ```

    Everything not published in Logfire keeps doing what the code says, and removing a published
    value in Logfire puts that piece back. A value Logfire cannot supply -- an unreachable Logfire, a
    missing value, one this release cannot parse -- means the same thing: the agent runs as written.

    Args:
        agent: The agent to manage, wired up in place. Its `name` is what the config is keyed on, so
            ADK's requirement that every agent have one is also this adapter's. Two things on it are
            replaced: `before_model_callback` and `after_model_callback` gain the managed hooks, and
            `model` is wrapped (see the documentation's *Known limits*).
        name: The name to key the config on, when it should differ from `agent.name`.
        label: The label to resolve, such as `'production'`. When `None`, the variable's own
            targeting rules and rollout choose which label this process gets.
        on_unmatched: What to do with a published value that reaches nothing in this deployment --
            an instruction id this agent does not assemble, an override naming a tool it does not
            advertise, a setting ADK or the model serving the request has no knob for. `'warn'` (the
            default) says so once per process; `'error'` fails the request; `'ignore'` says nothing.
        publish_baseline: Whether to publish the agent as this adapter observes it to Logfire, which
            is what the editor diffs published values against. Disable it when the variables token is
            intentionally read-only.
        logfire_instance: The Logfire instance to resolve and publish through. Defaults to the global
            one, which is what `logfire.configure()` sets up.

    Returns:
        The same `LlmAgent`, with the managed hooks installed.
    """

@dataclass(frozen=True)
class _Request:
    """What one model request resolved, carried from the hook before it to the work after it."""
    invocation_id: str
    resolution: Resolution
    code_names: dict[str, str]

class _Adapter:
    """The per-request work of managing one agent, and the state that outlives a request.

    An instance is shared by every run of its agent, so what it holds has to be safe to share: the
    control (which is), the model wrapper (which caches only resolved models by name), a flag saying
    the baseline has been described once, and a `ContextVar` holding what the request running *in
    this task* resolved. Two concurrent runs are two tasks with two contexts, so neither can see the
    other's renames or report the other's version.
    """
    def __init__(self, agent: LlmAgent, control: AgentControl) -> None: ...
    async def before_model(self, callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        """Describe this request to Logfire, and apply to it whatever Logfire has published.

        ADK assembles the whole request -- prompt, tools, model name, settings -- before calling this,
        and sends what it finds here afterwards, so this one hook reaches all four sections of the
        config. Returning `None` is what lets the request proceed.
        """
    def after_model(self, callback_context: CallbackContext, llm_response: LlmResponse) -> None:
        """Translate a renamed call back into the name the code gave it, before ADK dispatches it.

        Returning `None` is what leaves the response ADK's own; the translation is a replacement of
        the parts that name a tool, which is what the rest of the invocation goes on to read.
        """
