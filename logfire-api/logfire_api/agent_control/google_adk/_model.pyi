from .. import Resolution as Resolution
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager
from google.adk.models import LlmCapabilities
from google.adk.models.base_llm import BaseLlm
from google.adk.models.base_llm_connection import BaseLlmConnection as BaseLlmConnection
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse as LlmResponse

GOOGLE_PROVIDER: str
VERTEX_PROVIDER: str

def to_adk_model_name(model: str) -> str:
    """Translate a published `provider:model` into the string ADK's registry routes.

    A string with no `:` is a framework-native ADK name and passes through untouched, which is what
    lets someone publish `gemini-2.5-flash` or an ADK `Class:model` override and have it work.
    """
def to_canonical_model_name(model: str) -> str:
    """Describe an ADK model name in the contract's `provider:model` form, for the code baseline.

    LiteLLM's `provider/model` is the same statement with a different separator, so it translates
    exactly. A bare name is classified by its family, and a name from neither shape is left alone.
    """

class ManagedLlm(BaseLlm):
    """The agent's model, with the class that serves a request chosen per request.

    ADK picks the `BaseLlm` off the agent *after* `before_model_callback` runs but reads
    `llm_request.model` inside it, so a published name from the same provider family needs nothing
    but that field. A published name from a *different* provider needs a different class, and there
    is no hook that can supply one. This wrapper is where that happens: it is what the agent's
    `model` becomes, it reports the code model's name so an unmanaged request is byte-for-byte what
    it was, and it delegates each request to whichever model the callback resolved.

    Instances are shared across concurrent runs of one agent, so it holds no per-request state; the
    resolved models it caches are keyed by name and safe to reuse.
    """
    code_model: BaseLlm
    current_resolution: Callable[[], Resolution | None]
    @property
    def capabilities(self) -> LlmCapabilities:
        """The code model's own capabilities, so wrapping an agent's model does not narrow it.

        ADK asks the model what it supports rather than inferring it from the name, and the base
        implementation falls back to inferring it. Forwarding is what keeps a model that declares a
        capability -- Gemini pairing an output schema with tools, say -- declaring it once managed.
        """
    def connect(self, llm_request: LlmRequest) -> AbstractAsyncContextManager[BaseLlmConnection]:
        """Open a live connection on the code model.

        Live (bidirectional) runs are not managed: ADK builds that connection from the agent's model
        rather than from a per-request name, so there is nothing for a published `model` to change,
        and the agent connects exactly as written.
        """
    def resolve(self, name: str) -> BaseLlm | None:
        """The model that will serve `name` on the next request, or `None` when ADK cannot route it.

        Called from the per-request hook rather than from `generate_content_async`, so that a
        published model ADK cannot route is reported where every other unapplicable published value
        is -- before the request goes out, under the adapter's `on_unmatched` policy -- instead of
        raising from inside the model call. The model itself is what comes back rather than a
        yes-or-no, because what it *is* decides which settings the request may carry.
        """
    def serving(self, name: str | None) -> BaseLlm:
        """Which model a request naming `name` will actually be sent to."""
    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        """Delegate to the model `llm_request.model` names, which the hook has already resolved."""
