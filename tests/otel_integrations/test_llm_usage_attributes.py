from __future__ import annotations

from typing import Any

import pydantic
from anthropic.types import Message as AnthropicMessage, Usage as AnthropicUsage
from inline_snapshot import snapshot
from openai.types.create_embedding_response import CreateEmbeddingResponse, Usage as EmbeddingUsage
from openai.types.responses import Response
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails, ResponseUsage

from logfire._internal.integrations.llm_providers.anthropic import get_anthropic_usage_attributes
from logfire._internal.integrations.llm_providers.openai import get_openai_usage_attributes
from logfire._internal.integrations.llm_providers.usage import get_usage_attributes

try:
    import genai_prices  # noqa: F401  # pyright: ignore[reportUnusedImport]

    GENAI_PRICES_AVAILABLE = True
except Exception:
    GENAI_PRICES_AVAILABLE = False  # pyright: ignore[reportConstantRedefinition]


class FakeUsage(pydantic.BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class FakeResponse(pydantic.BaseModel):
    model: str
    usage: dict[str, int]


def test_tokens_and_raw() -> None:
    usage = FakeUsage(prompt_tokens=10, completion_tokens=5)
    response = FakeResponse(model='gpt-4', usage={'prompt_tokens': 10, 'completion_tokens': 5})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='openai', api_flavor='chat')
    if GENAI_PRICES_AVAILABLE:
        assert result.pop('operation.cost') == snapshot(0.0006)
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 10,
            'gen_ai.usage.output_tokens': 5,
            'gen_ai.usage.raw': {'prompt_tokens': 10, 'completion_tokens': 5},
        }
    )


def test_none_tokens() -> None:
    """When tokens are None, those attributes are omitted."""
    usage = FakeUsage()
    response = FakeResponse(model='gpt-4', usage={})
    result = get_usage_attributes(response, usage, None, None, provider_id='openai', api_flavor='chat')
    assert result == snapshot({'gen_ai.usage.raw': {}})


def test_no_model_dump() -> None:
    """When usage has no model_dump, USAGE_RAW is omitted."""
    usage = object()  # no model_dump
    response = FakeResponse(model='gpt-4', usage={})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='openai', api_flavor='chat')
    assert result == snapshot({'gen_ai.usage.input_tokens': 10, 'gen_ai.usage.output_tokens': 5})


def test_api_flavor_none() -> None:
    """When api_flavor is None, extract_usage is called without it."""
    usage = FakeUsage(input_tokens=10, output_tokens=5)
    response = FakeResponse(model='claude-3-haiku-20240307', usage={'input_tokens': 10, 'output_tokens': 5})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='anthropic')
    if GENAI_PRICES_AVAILABLE:
        assert result.pop('operation.cost') == snapshot(8.75e-06)
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 10,
            'gen_ai.usage.output_tokens': 5,
            'gen_ai.usage.raw': {'input_tokens': 10, 'output_tokens': 5},
        }
    )


def test_cost_failure_does_not_prevent_tokens() -> None:
    """Cost calculation failure must not prevent token attributes from being set."""
    usage = FakeUsage(prompt_tokens=10, completion_tokens=5)

    class BadResponse:
        def model_dump(self) -> dict[str, object]:
            raise RuntimeError('model_dump exploded')

    result = get_usage_attributes(BadResponse(), usage, 10, 5, provider_id='openai', api_flavor='chat')
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 10,
            'gen_ai.usage.output_tokens': 5,
            'gen_ai.usage.raw': {'prompt_tokens': 10, 'completion_tokens': 5},
        }
    )


def test_raw_usage_failure_does_not_prevent_cost() -> None:
    """Raw usage failure must not prevent cost from being calculated."""

    class BadUsage:
        def model_dump(self) -> dict[str, object]:
            raise RuntimeError('model_dump exploded')

    response = FakeResponse(model='gpt-4', usage={'prompt_tokens': 10, 'completion_tokens': 5})
    result = get_usage_attributes(response, BadUsage(), 10, 5, provider_id='openai', api_flavor='chat')
    if GENAI_PRICES_AVAILABLE:
        assert result.pop('operation.cost') == snapshot(0.0006)
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 10,
            'gen_ai.usage.output_tokens': 5,
        }
    )


def test_unknown_model_no_cost() -> None:
    """Unknown model should silently skip cost."""
    usage = FakeUsage(prompt_tokens=10, completion_tokens=5)
    response = FakeResponse(model='unknown-model-xyz', usage={'prompt_tokens': 10, 'completion_tokens': 5})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='openai', api_flavor='chat')
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 10,
            'gen_ai.usage.output_tokens': 5,
            'gen_ai.usage.raw': {'prompt_tokens': 10, 'completion_tokens': 5},
        }
    )


def test_model_none_from_extract_usage() -> None:
    """When extract_usage returns model=None, cost is skipped."""
    usage = FakeUsage(prompt_tokens=10)

    class NoModelResponse:
        def model_dump(self, **kwargs: Any) -> dict[str, object]:
            return {'usage': {'prompt_tokens': 10}}  # no 'model' key

    # Use embeddings flavor so extract_usage succeeds (doesn't require completion_tokens)
    # but returns model=None due to missing 'model' key
    result = get_usage_attributes(NoModelResponse(), usage, 10, None, provider_id='openai', api_flavor='embeddings')
    assert result == snapshot({'gen_ai.usage.input_tokens': 10, 'gen_ai.usage.raw': {'prompt_tokens': 10}})


# --- Tests for get_openai_usage_attributes ---


class FakeOpenAIResponse(pydantic.BaseModel):
    """Response with usage as a FakeUsage (for get_openai_usage_attributes tests)."""

    model: str
    usage: FakeUsage | None = None


def test_openai_usage_chat_completion() -> None:
    """Chat completion response (not Response or CreateEmbeddingResponse) gets api_flavor='chat'."""
    response = FakeOpenAIResponse(model='gpt-4', usage=FakeUsage(prompt_tokens=10, completion_tokens=5))
    result = get_openai_usage_attributes(response)
    if GENAI_PRICES_AVAILABLE:
        assert result.pop('operation.cost') == snapshot(0.0006)
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 10,
            'gen_ai.usage.output_tokens': 5,
            'gen_ai.usage.raw': {'prompt_tokens': 10, 'completion_tokens': 5},
        }
    )


def test_openai_usage_responses_api() -> None:
    """Response API response gets api_flavor='responses'."""
    usage = ResponseUsage.model_construct(
        input_tokens=20,
        output_tokens=10,
        input_tokens_details=InputTokensDetails.model_construct(cached_tokens=0),
        output_tokens_details=OutputTokensDetails.model_construct(reasoning_tokens=0),
        total_tokens=30,
    )
    response = Response.model_construct(
        id='resp_123',
        model='gpt-4o',
        created_at=0.0,
        object='response',
        output=[],
        parallel_tool_calls=True,
        tool_choice='auto',
        tools=[],
        usage=usage,
    )
    result = get_openai_usage_attributes(response)
    if GENAI_PRICES_AVAILABLE:
        assert result.pop('operation.cost') == snapshot(0.00015)
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 20,
            'gen_ai.usage.output_tokens': 10,
            'gen_ai.usage.raw': {
                'input_tokens': 20,
                'input_tokens_details': {'cached_tokens': 0},
                'output_tokens': 10,
                'output_tokens_details': {'reasoning_tokens': 0},
                'total_tokens': 30,
            },
        }
    )


def test_openai_usage_embeddings() -> None:
    """Embeddings response gets api_flavor='embeddings'."""
    emb_usage = EmbeddingUsage(prompt_tokens=15, total_tokens=15)
    response = CreateEmbeddingResponse(data=[], model='text-embedding-3-small', object='list', usage=emb_usage)
    result = get_openai_usage_attributes(response)
    if GENAI_PRICES_AVAILABLE:
        assert result.pop('operation.cost') == snapshot(3e-07)
    assert result == snapshot(
        {'gen_ai.usage.input_tokens': 15, 'gen_ai.usage.raw': {'prompt_tokens': 15, 'total_tokens': 15}}
    )


def test_openai_usage_none() -> None:
    """Response with usage=None returns empty dict."""
    response = FakeOpenAIResponse(model='gpt-4', usage=None)
    result = get_openai_usage_attributes(response)
    assert result == snapshot({})


# --- Tests for get_anthropic_usage_attributes ---


def test_anthropic_usage_basic() -> None:
    """Basic Anthropic usage with no cache tokens."""
    usage = AnthropicUsage.model_construct(input_tokens=10, output_tokens=5)
    response = AnthropicMessage.model_construct(
        model='claude-3-haiku-20240307',
        usage=usage,
    )
    result = get_anthropic_usage_attributes(response)
    if GENAI_PRICES_AVAILABLE:
        result.pop('operation.cost')
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 10,
            'gen_ai.usage.output_tokens': 5,
            'gen_ai.usage.raw': {'input_tokens': 10, 'output_tokens': 5},
        }
    )


def test_anthropic_usage_with_cache_tokens() -> None:
    """Anthropic usage with cache_read and cache_creation tokens adds to input_tokens."""
    usage = AnthropicUsage.model_construct(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=2,
    )
    response = AnthropicMessage.model_construct(
        model='claude-3-haiku-20240307',
        usage=usage,
    )
    result = get_anthropic_usage_attributes(response)
    if GENAI_PRICES_AVAILABLE:
        result.pop('operation.cost')
    assert result == snapshot(
        {
            'gen_ai.usage.input_tokens': 15,
            'gen_ai.usage.output_tokens': 5,
            'gen_ai.usage.raw': {
                'input_tokens': 10,
                'output_tokens': 5,
                'cache_read_input_tokens': 3,
                'cache_creation_input_tokens': 2,
            },
        }
    )


def test_anthropic_usage_none() -> None:
    """When usage is None, returns empty dict."""
    response = AnthropicMessage.model_construct(
        model='claude-3-haiku-20240307',
        usage=None,
    )
    assert get_anthropic_usage_attributes(response) == snapshot({})


def test_openai_embeddings_model_dump_uses_include() -> None:
    """For OpenAI embeddings, model_dump must be called with include={'model', 'usage'} only."""
    dump_calls: list[dict[str, Any]] = []

    class TrackingResponse:
        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            dump_calls.append(kwargs)
            return {'model': 'text-embedding-3-small', 'usage': {'prompt_tokens': 10, 'total_tokens': 10}}

    result = get_usage_attributes(TrackingResponse(), object(), 10, None, provider_id='openai', api_flavor='embeddings')
    assert result.get('gen_ai.usage.input_tokens') == 10
    if GENAI_PRICES_AVAILABLE:
        assert dump_calls
        assert dump_calls[0].get('include') == {'model', 'usage'}


def test_non_target_flavors_use_plain_model_dump() -> None:
    """chat, responses, api_flavor=None, and non-OpenAI embeddings must call plain model_dump()
    with no kwargs — preserving access to all response fields for genai-prices (e.g. 'output'
    for tool-call counting in pydantic/genai-prices#290)."""
    cases = [
        ('openai', 'chat'),
        ('openai', 'responses'),
        ('anthropic', None),
        ('google', 'embeddings'),
    ]
    for provider_id, flavor in cases:
        dump_calls: list[dict[str, Any]] = []

        class TrackingResponse:
            def model_dump(self, **kwargs: Any) -> dict[str, Any]:
                dump_calls.append(kwargs)
                return {'model': 'gpt-4', 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}

        result = get_usage_attributes(TrackingResponse(), object(), 10, 5, provider_id=provider_id, api_flavor=flavor)
        assert result.get('gen_ai.usage.input_tokens') == 10
        if GENAI_PRICES_AVAILABLE:
            assert len(dump_calls) == 1, f'expected exactly one model_dump call for {provider_id}/{flavor}'
            assert dump_calls[0] == {}, f'expected no kwargs for {provider_id}/{flavor}'
