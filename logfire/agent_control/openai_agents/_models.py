"""Translating between the contract's `provider:model` strings and the SDK's `prefix/model` ones.

Agent Control publishes one model string that has to mean the same thing to every framework, and the
OpenAI Agents SDK routes on a convention of its own: `MultiProvider` splits a name on its first `/`
and treats the part before it as a provider prefix, where no prefix and `openai/` mean OpenAI, and
`litellm/` and `any-llm/` mean "the rest of the world, via that gateway". These two functions are the
whole translation, in both directions, and neither of them ever invents a routing the SDK would
reject: a name they cannot classify is passed through untouched, which is also how a framework-native
id someone typed into Logfire keeps working.
"""

from __future__ import annotations

from collections.abc import Mapping

GATEWAY_PREFIXES = ('litellm', 'any-llm')
"""SDK prefixes whose remainder is itself a `<provider>/<model>` pair, so a provider id is readable.

`MultiProvider` sends both to a gateway that speaks every provider, which is why they are the only
prefixes a canonical `provider:model` can be built from or lowered into. A prefix a user registered
through `MultiProviderMap` names a provider only that process knows, so it stays as written.
"""

GATEWAY_PROVIDER_IDS: Mapping[str, str] = {
    'google': 'gemini',
    'google-cloud': 'vertex_ai',
    'fireworks': 'fireworks_ai',
    'together': 'together_ai',
    'moonshotai': 'moonshot',
    'bedrock-mantle': 'bedrock_mantle',
    'vercel': 'vercel_ai_gateway',
}
"""Canonical provider id -> the id the gateway knows that provider by, where the two genuinely differ.

The contract's provider ids are Pydantic AI's, and the gateway agrees with most of them: `anthropic`,
`groq`, `mistral`, `cohere`, `bedrock`, `azure`, `deepseek`, `xai`, `cerebras`, `github`, `heroku`,
`huggingface`, `nebius`, `ollama`, `openrouter`, `ovhcloud`, `sambanova`, `snowflake` and `zai` are
spelled the same on both sides and need no entry here. The entries above are the ones checked, name
against name, against the gateway's own provider list -- untranslated, each would become a
`litellm/<canonical id>/<model>` route that resolves to nothing.

A provider id with no entry goes to the gateway as written rather than guessed at, which is the rule
the rest of this module follows too. That deliberately leaves a few canonical ids the gateway has no
one spelling for: `openai-chat` and `openai-responses` name an API dialect rather than a vendor, and
which of the two an OpenAI model speaks is a property of the client the SDK was configured with, not
of a model name; `alibaba`, `crusoe` and the embedding-only providers have no name-for-name
counterpart to check against.
"""

LEGACY_PROVIDER_IDS: Mapping[str, str] = {
    'google-gla': 'google',
    'google-vertex': 'google-cloud',
}
"""Provider ids the contract has retired -> the current one, accepted on the way in and never emitted.

Pydantic AI v2 renamed the two Google providers: the Gemini API is `google` (which is also what
`GoogleProvider.name`, and so `gen_ai.system`, reports) and Vertex AI is `google-cloud`. A config
published against a v1-era agent can still carry the old spelling, so both are read here; nothing
writes them back out, so a baseline and a round trip through these two functions always say the
current id.
"""

_CANONICAL_PROVIDER_IDS: Mapping[str, str] = {gateway: canonical for canonical, gateway in GATEWAY_PROVIDER_IDS.items()}
"""The inverse of `GATEWAY_PROVIDER_IDS`, so a name round-trips through both functions unchanged."""


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
    provider, separator, name = model.partition(':')
    if not separator:
        return model
    provider = LEGACY_PROVIDER_IDS.get(provider, provider)
    if provider == 'openai':
        return name
    return f'litellm/{GATEWAY_PROVIDER_IDS.get(provider, provider)}/{name}'


def to_canonical_model_name(model: str) -> str:
    """Raise an SDK model name to the canonical `provider:model` form, for the baseline.

    The inverse of `to_sdk_model_name` wherever the SDK name carries a provider id: a bare name is
    OpenAI's, and `litellm/anthropic/claude-fable-5-1` names Anthropic. A name that does not carry
    one -- `litellm/some-gateway-alias` with nothing to split, a prefix from a `MultiProviderMap`
    that only this process can resolve -- is published as written rather than guessed at, so the
    baseline says what the code says and a round trip through `to_sdk_model_name` returns it intact.
    """
    prefix, separator, rest = model.partition('/')
    if not separator:
        return f'openai:{model}'
    if prefix == 'openai':
        return f'openai:{rest}'
    if prefix in GATEWAY_PREFIXES:
        provider, gateway_separator, name = rest.partition('/')
        if gateway_separator:
            return f'{_CANONICAL_PROVIDER_IDS.get(provider, provider)}:{name}'
    return model
