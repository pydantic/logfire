# OpenAI Streaming Usage Attributes — Code Spec

**This implements the prose spec in [spec](spec.md), which is the primary source of truth.**

## Modified: `OpenaiChatCompletionStreamState.get_attributes()` in `openai.py`

*(implements "Each streaming state's `get_attributes()` calls `get_usage_attributes()`", "The reconstructed response object serves as the `response` parameter")*

Currently, `get_attributes()` builds `result` from `span_data`, adds `response_data` (version 1) and `OUTPUT_MESSAGES` (latest), and returns. The change adds a usage extraction block:

```python
def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
    versions = self._versions
    result = dict(**span_data)
    if 1 in versions:
        result['response_data'] = self.get_response_data()
    if 'latest' in versions:
        # ... existing output messages logic (unchanged) ...

    try:
        final_completion = self._stream_state.current_completion_snapshot
        usage = final_completion.usage
        if usage is not None:
            input_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', None))
            output_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', None))
            result.update(
                get_usage_attributes(final_completion, usage, input_tokens, output_tokens,
                                     provider_id='openai', api_flavor='chat')
            )
    except Exception:
        pass

    return result
```

The `current_completion_snapshot` access is already done earlier in the method (for the `'latest'` version output messages). This separate `try/except` ensures usage errors don't affect other attributes. The `final_completion` is a `ChatCompletion` — the same type `on_response()` handles for non-streaming. Token extraction uses the same `getattr` fallback pattern.

## Modified: `OpenaiResponsesStreamState.get_attributes()` in `openai.py`

*(implements "Each streaming state's `get_attributes()` calls `get_usage_attributes()`", "The reconstructed response object serves as the `response` parameter")*

Currently, `get_attributes()` calls `self.get_response_data()` to get the `Response` object, uses it for output messages/events, and returns `span_data` (mutated). The change adds a usage extraction block:

```python
def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
    versions = self._versions
    response = self.get_response_data()
    if response:
        # ... existing output messages and events logic (unchanged) ...

        try:
            usage = response.usage
            if usage is not None:
                input_tokens = getattr(usage, 'input_tokens', None)
                output_tokens = getattr(usage, 'output_tokens', None)
                span_data.update(
                    get_usage_attributes(response, usage, input_tokens, output_tokens,
                                         provider_id='openai', api_flavor='responses')
                )
        except Exception:
            pass

    return span_data
```

The `response` is a `Response` object — same type as non-streaming. The Responses API always uses `input_tokens`/`output_tokens` directly (no fallback needed), but using `getattr` keeps it safe. The usage block is inside the `if response:` guard since there's no usage without a response.

## Not changed

- `get_usage_attributes()` in `usage.py` — no changes needed, the existing function handles everything.
- `OpenaiCompletionStreamState` — legacy text completions, out of scope.
- `llm_provider.py` / `record_streaming()` — no changes needed, it already passes `get_attributes()` result as kwargs.
- `types.py` / `StreamState` base class — no changes needed.
