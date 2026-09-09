from .. import to_milliseconds as to_milliseconds
from _typeshed import Incomplete
from collections.abc import Mapping
from dataclasses import dataclass
from google.adk.models.base_llm import BaseLlm
from google.genai import types
from typing import Any

CONFIGURABLE: Incomplete

@dataclass(frozen=True)
class Backend:
    """What one family of ADK model classes actually reads out of a `GenerateContentConfig`.

    ADK's request object is Gemini-shaped, and its other backends translate the parts of it they
    understand. Applying a setting the backend does not translate is not a smaller change than
    intended -- it is no change at all, with the Logfire UI showing a value the agent never used, so
    it belongs under `on_unmatched` like any other published value that reached nothing.

    A backend that hands the config straight to a provider has a second reason to leave a setting
    off: one the *provider* refuses is not ignored, it fails the request, which is the one thing a
    published value must never be able to do. Those are recorded here too, against the observed
    behaviour of the API rather than against ADK's source -- see the tests that record it live.
    """
    label: str
    settings: frozenset[str]
    thinking_levels: bool

UNKNOWN_BACKEND: Incomplete

def backend_of(model: BaseLlm) -> Backend:
    """What the model serving a request reads, found through the class it inherits from.

    ADK's own subclasses -- `Gemma` on top of `Gemini`, `Gemma3Ollama` on top of `LiteLlm` -- read
    what their base reads, so the whole MRO is walked rather than the exact class matched.

    The Gemini client is the one that then asks the model's *name* a second question, because it
    forwards the request config untranslated: what reaches the provider is decided by the model
    rather than by the class, and the two Gemini generations disagree about how to ask for thinking.
    """
def apply(config: types.GenerateContentConfig, settings: Mapping[str, Any], backend: Backend) -> list[str]:
    """Merge a canonical settings patch into one request's config, in place.

    The config is ADK's per-request copy of the agent's own, so writing to it changes this request
    and nothing else. Only what `backend` reads is written: a setting this request's model would
    ignore is left off the request entirely rather than set where the Logfire UI can see it and the
    model cannot. Returns a message for every setting that went unapplied for either reason -- the
    backend does not read that key, or does not read that value -- for the caller to report under its
    `on_unmatched` policy.
    """
def describe(config: types.GenerateContentConfig | None, backend: Backend) -> dict[str, Any]:
    """The agent's own settings in the contract's canonical names, for the code baseline.

    Only the canonical keys are described, and only the ones the agent's own model reads. A
    `GenerateContentConfig` also carries provider-specific settings and `http_options.headers`, which
    is where an authorization header lives, and the baseline is published where every member of the
    Logfire project can read it. A setting the agent sets and its backend ignores is left out for a
    different reason: the baseline is what the editor presents as the truth about the code, and a
    value the agent never actually sends is not part of that truth.
    """
