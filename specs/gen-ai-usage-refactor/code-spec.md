# Refactor GenAI Usage Attributes — Code Spec

**This implements the prose spec in [spec](spec.md), which is the primary source of truth.**

**New file: `logfire/_internal/integrations/llm_providers/usage.py`** *(implements "Everything else about setting usage attributes")*

```python
def get_usage_attributes(
    response: Any,
    usage: Any,
    input_tokens: int | None,
    output_tokens: int | None,
    provider_id: str,
    api_flavor: str | None = None,
) -> dict[str, Any]:
    """Build usage attributes: INPUT_TOKENS, OUTPUT_TOKENS, USAGE_RAW, operation.cost.

    Callers extract input/output tokens themselves (API-surface-specific).
    response is the full API response object, passed to genai_prices for cost calculation
    (genai_prices extracts both model and usage from it). usage is the usage sub-object,
    used for USAGE_RAW. api_flavor is only needed for OpenAI ('chat' or 'responses').
    Returns only attributes that have values.
    """
```

**Call site — `openai.py` `on_response()`, replacing lines 594–622:** *(implements "This spec covers only the refactoring step")*

```python
usage = getattr(response, 'usage', None)
if usage is not None:
    if isinstance(response, Response):
        input_tokens = getattr(usage, 'input_tokens', None)
        output_tokens = getattr(usage, 'output_tokens', None)
        api_flavor = 'responses'
    else:
        input_tokens = getattr(usage, 'prompt_tokens', None)
        output_tokens = getattr(usage, 'completion_tokens', None)
        api_flavor = 'chat'
    span.set_attributes(
        get_usage_attributes(response, usage, input_tokens, output_tokens,
                             provider_id='openai', api_flavor=api_flavor)
    )
```

This replaces the inline token-setting code and the `genai_prices` try/except block. The `getattr` chain for extracting the usage object from the response stays. Response-type-specific logic (`response_data`, `OUTPUT_MESSAGES`, `RESPONSE_FINISH_REASONS`) is unchanged.

**Not changed in this PR:**

- `anthropic.py` `on_response()` — continues using inline usage logic. Will be refactored in a follow-up to call `get_usage_attributes`, which will also add `USAGE_RAW`.
- OpenAI streaming `get_attributes()` methods — remain unchanged. Follow-up will add `result.update(get_usage_attributes(...))` calls.
- Anthropic streaming — unchanged. Follow-up will first extend `AnthropicMessageStreamState` to capture usage events, then call `get_usage_attributes`.
