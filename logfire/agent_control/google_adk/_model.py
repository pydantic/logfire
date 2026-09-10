"""Switching an ADK agent's model from Logfire, in both directions the contract needs.

ADK names a model with a bare string that a regex registry routes to a `BaseLlm` class, and Agent
Control names one with Pydantic AI's canonical `provider:model`. Two things have to bridge that: a
translation table, and a model object that can change which class serves a request -- because ADK's
per-request hook can only change the model *name* on the request, while the class that reads it was
chosen from the agent before the hook ran.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, nullcontext

from google.adk.models import LlmCapabilities
from google.adk.models.base_llm import BaseLlm
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models.registry import LLMRegistry
from pydantic import PrivateAttr

from .. import Resolution

GOOGLE_PROVIDER = 'google'
"""The canonical provider id for the Gemini API, which is also what `gen_ai.system` carries.

Pydantic AI's `GoogleProvider.name`, and so the id the Logfire UI shows next to a Gemini span. The
ADK name a Gemini model is written with says nothing about which of Google's two APIs will serve it
-- one `Gemini` class reads `GOOGLE_GENAI_USE_VERTEXAI` to decide -- so a bare name is described with
this one, the id the request will be attributed to in the common case.
"""

VERTEX_PROVIDER = 'google-cloud'
"""The canonical provider id for Vertex AI."""

_PROVIDER_PREFIXES: dict[str, str] = {
    # Gemini and Claude are ADK's own registry entries, matched on the bare model name.
    # Current ids, as Pydantic AI v2 spells them:
    GOOGLE_PROVIDER: '',
    VERTEX_PROVIDER: '',
    'anthropic': '',
    # Legacy ids, accepted as input and never emitted: Pydantic AI v1 spelled the two Google
    # providers this way, and a config published against a v1-era agent still carries them. v2
    # renamed `google-gla` to `google` and `google-vertex` to `google-cloud`, and refuses both of
    # the old ones outright, so translating them here is the difference between a published model
    # that still works after the upgrade and one that silently reaches nothing.
    'google-gla': '',
    'google-vertex': '',
    # Everything else reaches ADK through LiteLLM's `provider/model`, which is also the fallback for
    # a provider this table has never heard of -- LiteLLM knows well over a hundred of them, and its
    # convention is exactly `provider/model`, so guessing it is far better than refusing the switch.
    'openai': 'openai/',
}
"""How a canonical `provider:model` becomes the string ADK's `LLMRegistry` routes.

Only the providers whose ADK form is *not* `provider/model` need an entry. `openai` is listed
because ADK has two routes for it -- a bare `gpt-*` served by its own OpenAI class, and LiteLLM's
`openai/gpt-*` -- and the LiteLLM one is the one that works with the extra people actually install
for cross-provider ADK agents (`google-adk[extensions]`).
"""

_ADK_PREFIX_PROVIDERS: dict[str, str] = {
    'gemini': GOOGLE_PROVIDER,
    'gemma': GOOGLE_PROVIDER,
    'claude': 'anthropic',
    'gpt': 'openai',
}
"""How a bare ADK model name is classified for the code baseline, by its first `-`-separated word.

Only current provider ids are emitted, since the baseline is what the editor offers as the starting
point for a published value and a legacy id there would be a value nothing downstream can resolve.

The baseline is documentation, so a name this table cannot classify is published exactly as the code
wrote it rather than guessed at: a wrong provider in the editor is worse than a name without one.
"""


def to_adk_model_name(model: str) -> str:
    """Translate a published `provider:model` into the string ADK's registry routes.

    A string with no `:` is a framework-native ADK name and passes through untouched, which is what
    lets someone publish `gemini-2.5-flash` or an ADK `Class:model` override and have it work.
    """
    provider, separator, name = model.partition(':')
    if not separator:
        return model
    prefix = _PROVIDER_PREFIXES.get(provider)
    return f'{provider}/{name}' if prefix is None else f'{prefix}{name}'


def to_canonical_model_name(model: str) -> str:
    """Describe an ADK model name in the contract's `provider:model` form, for the code baseline.

    LiteLLM's `provider/model` is the same statement with a different separator, so it translates
    exactly. A bare name is classified by its family, and a name from neither shape is left alone.
    """
    provider, separator, name = model.partition('/')
    if separator:
        return f'{provider}:{name}'
    provider = _ADK_PREFIX_PROVIDERS.get(model.split('-')[0], '')
    return f'{provider}:{model}' if provider else model


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
    """The model the agent was written with, which serves every request nothing is published for."""

    current_resolution: Callable[[], Resolution | None]
    """This request's resolution, for putting its label and version back on the model call's spans.

    ADK opens its `call_llm` span and *then* calls `before_model_callback`, so the block that resolves
    the config cannot be the block the model call happens in: by the time the request goes out, the
    context the adapter resolved in has been left. This is how it is re-entered, as close to the
    provider as the framework allows -- everything the model call itself emits, including whatever
    instrumentation the provider's own client carries, is inside it.
    """

    _resolved: dict[str, BaseLlm] = PrivateAttr(default_factory=dict[str, BaseLlm])

    @property
    def capabilities(self) -> LlmCapabilities:
        """The code model's own capabilities, so wrapping an agent's model does not narrow it.

        ADK asks the model what it supports rather than inferring it from the name, and the base
        implementation falls back to inferring it. Forwarding is what keeps a model that declares a
        capability -- Gemini pairing an output schema with tools, say -- declaring it once managed.
        """
        return self.code_model.capabilities

    def connect(self, llm_request: LlmRequest) -> AbstractAsyncContextManager[BaseLlmConnection]:
        """Open a live connection on the code model.

        Live (bidirectional) runs are not managed: ADK builds that connection from the agent's model
        rather than from a per-request name, so there is nothing for a published `model` to change,
        and the agent connects exactly as written.
        """
        return self.code_model.connect(llm_request)

    def resolve(self, name: str) -> BaseLlm | None:
        """The model that will serve `name` on the next request, or `None` when ADK cannot route it.

        Called from the per-request hook rather than from `generate_content_async`, so that a
        published model ADK cannot route is reported where every other unapplicable published value
        is -- before the request goes out, under the adapter's `on_unmatched` policy -- instead of
        raising from inside the model call. The model itself is what comes back rather than a
        yes-or-no, because what it *is* decides which settings the request may carry.
        """
        if name == self.code_model.model:
            return self.code_model
        if (resolved := self._resolved.get(name)) is not None:
            return resolved
        try:
            self._resolved[name] = LLMRegistry.new_llm(name)
        except (ValueError, ImportError):
            # `ValueError` is an unroutable name; `ImportError` is a name whose provider needs an
            # extra this deployment does not have installed. Both mean the same thing to the agent.
            return None
        return self._resolved[name]

    def serving(self, name: str | None) -> BaseLlm:
        """Which model a request naming `name` will actually be sent to."""
        return self._resolved.get(name or '', self.code_model)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Delegate to the model `llm_request.model` names, which the hook has already resolved."""
        llm = self.serving(llm_request.model)
        resolution = self.current_resolution()
        with resolution.reported() if resolution is not None else nullcontext():
            async for response in llm.generate_content_async(llm_request, stream=stream):
                yield response
