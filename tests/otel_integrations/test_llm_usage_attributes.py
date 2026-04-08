from __future__ import annotations

import pydantic
from inline_snapshot import snapshot

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
        def model_dump(self) -> dict[str, object]:
            return {'usage': {'prompt_tokens': 10}}  # no 'model' key

    # Use embeddings flavor so extract_usage succeeds (doesn't require completion_tokens)
    # but returns model=None due to missing 'model' key
    result = get_usage_attributes(NoModelResponse(), usage, 10, None, provider_id='openai', api_flavor='embeddings')
    assert result == snapshot({'gen_ai.usage.input_tokens': 10, 'gen_ai.usage.raw': {'prompt_tokens': 10}})
