# Anthropic Streaming Usage Attributes — Code Spec

**This implements the prose spec in [spec](spec.md), which is the primary source of truth.**

## Modified: `AnthropicMessageStreamState.__init__()` in `anthropic.py`

*(implements "record_chunk() uses the Anthropic SDK's accumulate_event()")*

```python
def __init__(self):
    self._message: Any = None
    self._chunk_count: int = 0
```

Replaces `self._content: list[str] = []`. The accumulated message holds both content and usage. `_message` is typed as `Any` because it can be either `ParsedMessage` or `ParsedBetaMessage`. `_chunk_count` tracks text delta events (not accumulated content blocks) to preserve the existing `chunk_count` semantics in `get_response_data()`.

## Modified: `AnthropicMessageStreamState.record_chunk()` in `anthropic.py`

*(implements "record_chunk() uses the Anthropic SDK's accumulate_event()")*

```python
def record_chunk(self, chunk: anthropic.types.MessageStreamEvent) -> None:
    if type(chunk).__module__.startswith('anthropic.types.beta'):
        self._message = beta_accumulate_event(
            event=cast(Any, chunk), current_snapshot=self._message, request_headers=httpx.Headers()
        )
    else:
        self._message = accumulate_event(event=chunk, current_snapshot=self._message)
    if isinstance(getattr(chunk, 'delta', None), (TextDelta, BetaTextDelta)):
        self._chunk_count += 1
```

Replaces the manual text extraction via `content_from_messages()`. Each chunk updates the accumulated message snapshot — content blocks, usage, stop reason, etc. Beta events are detected via module name (since `BetaRawMessageStreamEvent` is a Union type alias unusable with `isinstance`) and routed to `beta_accumulate_event`. Text delta events increment `_chunk_count` to track the number of streamed text chunks (distinct from accumulated content blocks).

## Modified: `AnthropicMessageStreamState.get_response_data()` in `anthropic.py`

*(implements "The manual text accumulation is replaced by reading from the accumulated message")*

```python
def get_response_data(self) -> Any:
    """Returns response data for the version 1 log format."""
```

Extracts `combined_chunk_content` from `self._message.content` (the accumulated content blocks) and `chunk_count` from `self._chunk_count` (the number of text delta stream events). Must produce the same dict shape as before: `{'combined_chunk_content': str, 'chunk_count': int}`. Note: `chunk_count` counts text delta events received during streaming, not the number of accumulated content blocks — `accumulate_event` merges deltas into blocks, so counting blocks would give a lower number.

## Modified: `AnthropicMessageStreamState.get_attributes()` in `anthropic.py`

*(implements "get_anthropic_usage_attributes() is reused for streaming", "Usage attributes are set regardless of semconv version", "Existing streaming behavior must not change")*

```python
def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
    versions = self._versions
    result = dict(**span_data)
    if 1 in versions:
        result['response_data'] = self.get_response_data()
    if 'latest' in versions and self._message and self._message.content:
        result[OUTPUT_MESSAGES] = [convert_response_to_semconv(self._message)]
    # Usage attributes — outside version-specific branches
    if self._message is not None:
        result.update(get_anthropic_usage_attributes(self._message))
    return result
```

The `'latest'` version block uses `convert_response_to_semconv()` — the same function used by non-streaming `on_response()` — to produce output messages with full content (text + tool_use parts) and `finish_reason`. The usage call reuses `get_anthropic_usage_attributes()`, also shared with the non-streaming path. This works because `accumulate_event` produces a `Message` with final accurate usage.

## New import in `anthropic.py`

```python
import httpx
from anthropic.lib.streaming._beta_messages import accumulate_event as beta_accumulate_event
from anthropic.lib.streaming._messages import accumulate_event
```

`httpx` is needed for the `request_headers` parameter of `beta_accumulate_event`. `TextDelta`/`BetaTextDelta` imports are retained (were already present) for the `_chunk_count` logic. `_message` is typed as `Any` (not `ParsedMessage`) to accommodate both regular and beta message types.

## Removed: `content_from_messages()` in `anthropic.py`

*(implements "The manual text accumulation is replaced by reading from the accumulated message")*

The helper that extracted text from `TextDelta`/`TextBlock` chunks was only called by `record_chunk()` and has no other references. Removed.

## Not changed

- `get_anthropic_usage_attributes()` — now reused for both streaming and non-streaming (no modifications needed).
- `get_usage_attributes()` in `usage.py` — no changes needed.
- `on_response()` — non-streaming path, unchanged.
- `llm_provider.py` / `record_streaming()` — already passes through `get_attributes()` result.
- `types.py` / `StreamState` base class — no changes needed.
