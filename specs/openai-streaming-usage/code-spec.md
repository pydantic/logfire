# OpenAI Streaming Usage Attributes — Code Spec

**This implements the prose spec in [spec](spec.md), which is the primary source of truth.**

## New: `get_openai_usage_attributes()` in `openai.py`

*(implements "The usage extraction logic must not be duplicated")*

```python
def get_openai_usage_attributes(response: Any) -> dict[str, Any]:
    """Extract usage attributes from any OpenAI response object.

    Works for ChatCompletion, Response, CreateEmbeddingResponse —
    both from non-streaming on_response() and streaming get_attributes().
    Returns an empty dict when usage is None.
    """
```

This function encapsulates the logic currently inline in `on_response()` (lines 595–609):
1. `usage = getattr(response, 'usage', None)` — bail with `{}` if None
2. Extract `input_tokens` and `output_tokens` via the existing `getattr` fallback (`prompt_tokens` → `input_tokens`, `completion_tokens` → `output_tokens`)
3. Determine `api_flavor` from response type: `isinstance(response, Response)` → `'responses'`, `isinstance(response, CreateEmbeddingResponse)` → `'embeddings'`, else `'chat'`
4. Return `get_usage_attributes(response, usage, input_tokens, output_tokens, provider_id='openai', api_flavor=api_flavor)`

Lives in `openai.py` rather than `usage.py` to keep `usage.py` provider-agnostic — the `isinstance` checks against OpenAI types are OpenAI-specific. No try/except — errors surface normally. `get_usage_attributes()` handles its own error isolation internally.

## Modified: `on_response()` in `openai.py`

*(implements "The usage extraction logic must not be duplicated")*

Replace the inline usage block (lines 595–609) with:

```python
span.set_attributes(get_openai_usage_attributes(response))
```

No behavioral change — same logic, just moved into the shared function.

## Modified: `OpenaiChatCompletionStreamState.get_attributes()` in `openai.py`

*(implements "Every OpenAI streaming span", "The reconstructed response object is the same type")*

Add after the existing version-specific blocks:

```python
try:
    final_completion = self._stream_state.current_completion_snapshot
except AssertionError:
    pass
else:
    result.update(get_openai_usage_attributes(final_completion))
```

The `try/except AssertionError` is narrow — it only catches the known case where `current_completion_snapshot` raises `AssertionError` when there's no snapshot (the same pattern already used at line 560 in the existing `'latest'` version block). The `get_openai_usage_attributes()` call itself is not wrapped — errors there should surface normally.

## Modified: `OpenaiResponsesStreamState.get_attributes()` in `openai.py`

*(implements "Every OpenAI streaming span", "The reconstructed response object is the same type")*

Add inside the existing `if response:` guard, after the version-specific blocks:

```python
span_data.update(get_openai_usage_attributes(response))
```

No try/except needed — `response` is already known to be non-None, and `get_openai_usage_attributes()` handles `usage is None` internally.

## Not changed

- `get_usage_attributes()` in `usage.py` — no changes needed.
- `OpenaiCompletionStreamState` — legacy text completions, out of scope.
- `llm_provider.py` / `record_streaming()` — already passes through `get_attributes()` result.
- `types.py` / `StreamState` base class — no changes needed.
