from __future__ import annotations

import pytest

from logfire._internal.integrations.llm_providers.usage import get_usage_attributes


def _has_genai_prices() -> bool:
    try:
        import genai_prices  # noqa: F401  # pyright: ignore[reportUnusedImport]

        return True
    except ImportError:
        return False


class FakeUsage:
    def __init__(self, **kwargs: int | None):
        self._data = kwargs

    def model_dump(self, exclude_none: bool = False) -> dict[str, int | None]:
        if exclude_none:
            return {k: v for k, v in self._data.items() if v is not None}
        return dict(self._data)


class FakeResponse:
    def __init__(self, model: str, usage: dict[str, int]):
        self.model = model
        self._usage = usage

    def model_dump(self) -> dict[str, object]:
        return {'model': self.model, 'usage': self._usage}


def test_tokens_and_raw() -> None:
    usage = FakeUsage(prompt_tokens=10, completion_tokens=5)
    response = FakeResponse('gpt-4', {'prompt_tokens': 10, 'completion_tokens': 5})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='openai', api_flavor='chat')
    assert result['gen_ai.usage.input_tokens'] == 10
    assert result['gen_ai.usage.output_tokens'] == 5
    assert result['gen_ai.usage.raw'] == {'prompt_tokens': 10, 'completion_tokens': 5}
    assert 'operation.cost' in result


def test_none_tokens() -> None:
    """When tokens are None, those attributes are omitted."""
    usage = FakeUsage()
    response = FakeResponse('gpt-4', {})
    result = get_usage_attributes(response, usage, None, None, provider_id='openai', api_flavor='chat')
    assert 'gen_ai.usage.input_tokens' not in result
    assert 'gen_ai.usage.output_tokens' not in result


def test_no_model_dump() -> None:
    """When usage has no model_dump, USAGE_RAW is omitted."""
    usage = object()  # no model_dump
    response = FakeResponse('gpt-4', {})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='openai', api_flavor='chat')
    assert 'gen_ai.usage.raw' not in result
    assert result['gen_ai.usage.input_tokens'] == 10


def test_api_flavor_none() -> None:
    """When api_flavor is None, extract_usage is called without it."""
    usage = FakeUsage(input_tokens=10, output_tokens=5)
    response = FakeResponse('claude-3-haiku-20240307', {'input_tokens': 10, 'output_tokens': 5})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='anthropic')
    assert result['gen_ai.usage.input_tokens'] == 10


def test_cost_failure_does_not_prevent_tokens() -> None:
    """Cost calculation failure must not prevent token attributes from being set."""
    usage = FakeUsage(prompt_tokens=10, completion_tokens=5)

    class BadResponse:
        def model_dump(self) -> dict[str, object]:
            raise RuntimeError('model_dump exploded')

    result = get_usage_attributes(BadResponse(), usage, 10, 5, provider_id='openai', api_flavor='chat')
    assert result['gen_ai.usage.input_tokens'] == 10
    assert result['gen_ai.usage.output_tokens'] == 5
    assert result['gen_ai.usage.raw'] == {'prompt_tokens': 10, 'completion_tokens': 5}
    assert 'operation.cost' not in result


def test_unknown_model_no_cost() -> None:
    """Unknown model should silently skip cost."""
    usage = FakeUsage(prompt_tokens=10, completion_tokens=5)
    response = FakeResponse('unknown-model-xyz', {'prompt_tokens': 10, 'completion_tokens': 5})
    result = get_usage_attributes(response, usage, 10, 5, provider_id='openai', api_flavor='chat')
    assert result['gen_ai.usage.input_tokens'] == 10
    assert 'operation.cost' not in result


@pytest.mark.skipif(
    not _has_genai_prices(),
    reason='genai_prices not installed',
)
def test_model_none_from_extract_usage() -> None:
    """When extract_usage returns model=None, cost is skipped."""
    usage = FakeUsage(prompt_tokens=10)

    class NoModelResponse:
        def model_dump(self) -> dict[str, object]:
            return {'usage': {'prompt_tokens': 10}}  # no 'model' key

    result = get_usage_attributes(NoModelResponse(), usage, 10, None, provider_id='openai', api_flavor='chat')
    assert result['gen_ai.usage.input_tokens'] == 10
    assert 'operation.cost' not in result
