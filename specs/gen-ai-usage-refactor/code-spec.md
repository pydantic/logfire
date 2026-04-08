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
    used for USAGE_RAW. api_flavor is needed for OpenAI ('chat', 'responses', or 'embeddings').
    Returns only attributes that have values.

    Token/raw-usage and cost fail independently — a cost error does not prevent tokens
    from being set. Cost errors are silently caught (expected for unknown models etc.).
    """
```

**Call site — `openai.py` `on_response()`, replacing the cost block (lines 594–608) and token/usage block (lines 614–622):** *(implements "This spec covers only the refactoring step", "Embeddings cost calculation is currently broken")*

The `response_id` handling between these two blocks (lines 610–613) is unchanged.

```python
usage = getattr(response, 'usage', None)
if usage is not None:
    input_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', None))
    output_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', None))
    if isinstance(response, Response):
        api_flavor = 'responses'
    elif isinstance(response, CreateEmbeddingResponse):
        api_flavor = 'embeddings'
    else:
        api_flavor = 'chat'
    span.set_attributes(
        get_usage_attributes(response, usage, input_tokens, output_tokens,
                             provider_id='openai', api_flavor=api_flavor)
    )
```

Token extraction uses the existing fallback `getattr` pattern, which works safely across all OpenAI API surfaces. The `api_flavor` is determined by response type — this fixes the current bug where embeddings get `api_flavor='chat'`. Response-type-specific logic (`response_data`, `OUTPUT_MESSAGES`, `RESPONSE_FINISH_REASONS`) is unchanged.

**Not changed in this PR:**

- `anthropic.py` `on_response()` — continues using inline usage logic. Will be refactored in a follow-up to call `get_usage_attributes`, which will also add `USAGE_RAW`.
- OpenAI streaming `get_attributes()` methods — remain unchanged. Follow-up will add `result.update(get_usage_attributes(...))` calls.
- Anthropic streaming — unchanged. Follow-up will first extend `AnthropicMessageStreamState` to capture usage events, then call `get_usage_attributes`.
