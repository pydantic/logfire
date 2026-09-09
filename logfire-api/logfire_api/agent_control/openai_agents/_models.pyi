from _typeshed import Incomplete
from collections.abc import Mapping

GATEWAY_PREFIXES: Incomplete
GATEWAY_PROVIDER_IDS: Mapping[str, str]
LEGACY_PROVIDER_IDS: Mapping[str, str]

def to_sdk_model_name(model: str) -> str:
    """Lower a canonical `provider:model` string into the name `MultiProvider` routes on.

    `'openai:gpt-5.6-luna'` becomes `'gpt-5.6-luna'`, since a bare name is exactly how the SDK spells
    an OpenAI model, and every other provider becomes `'litellm/<provider>/<model>'`, the SDK's own
    way to reach it -- under the id the gateway knows that provider by, which for a handful of
    providers is not the contract's own; see `GATEWAY_PROVIDER_IDS`. A string with no `':'` is
    already an SDK name -- `'gpt-5.6-luna'`, `'litellm/anthropic/claude-fable-5-1'`, a prefix
    registered through `MultiProviderMap` -- and is returned as written, which is what the contract
    asks of an adapter.

    An OpenAI-compatible endpoint reached through a `base_url` is still `openai:` here: the provider
    id names the API dialect, and which host answers it is the client's business, not the config's.
    """
def to_canonical_model_name(model: str) -> str:
    """Raise an SDK model name to the canonical `provider:model` form, for the baseline.

    The inverse of `to_sdk_model_name` wherever the SDK name carries a provider id: a bare name is
    OpenAI's, and `litellm/anthropic/claude-fable-5-1` names Anthropic. A name that does not carry
    one -- `litellm/some-gateway-alias` with nothing to split, a prefix from a `MultiProviderMap`
    that only this process can resolve -- is published as written rather than guessed at, so the
    baseline says what the code says and a round trip through `to_sdk_model_name` returns it intact.
    """
