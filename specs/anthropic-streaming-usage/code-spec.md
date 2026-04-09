# Anthropic Streaming Usage Attributes — Code Spec

**This implements the prose spec in [spec](spec.md), which is the primary source of truth.**

## Modified: `AnthropicMessageStreamState.__init__()` in `anthropic.py`

*(implements "record_chunk() uses the Anthropic SDK's accumulate_event()")*

```python
def __init__(self):
    self._message: ParsedMessage[object] | None = None
```

Replaces `self._content: list[str] = []`. The accumulated message holds both content and usage.

## Modified: `AnthropicMessageStreamState.record_chunk()` in `anthropic.py`

*(implements "record_chunk() uses the Anthropic SDK's accumulate_event()")*

```python
def record_chunk(self, chunk: anthropic.types.MessageStreamEvent) -> None:
    self._message = accumulate_event(event=chunk, current_snapshot=self._message)
```

Replaces the manual text extraction via `content_from_messages()`. Each chunk updates the accumulated message snapshot — content blocks, usage, stop reason, etc.

## Modified: `AnthropicMessageStreamState.get_response_data()` in `anthropic.py`

*(implements "The manual text accumulation is replaced by reading from the accumulated message")*

```python
def get_response_data(self) -> Any:
    """Returns response data for the version 1 log format."""
```

Extracts `combined_chunk_content` and `chunk_count` from `self._message.content` (the accumulated content blocks) instead of from `self._content`. Must produce the same dict shape as before: `{'combined_chunk_content': str, 'chunk_count': int}`.

## Modified: `AnthropicMessageStreamState.get_attributes()` in `anthropic.py`

*(implements "get_anthropic_usage_attributes() is reused for streaming", "Usage attributes are set regardless of semconv version", "Existing streaming behavior must not change")*

```python
def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
    versions = self._versions
    result = dict(**span_data)
    if 1 in versions:
        result['response_data'] = self.get_response_data()
    if 'latest' in versions and self._message and self._message.content:
        # extract text from self._message.content blocks
        ...
        result[OUTPUT_MESSAGES] = [OutputMessage(...)]
    # Usage attributes — outside version-specific branches
    if self._message is not None:
        result.update(get_anthropic_usage_attributes(self._message))
    return result
```

The `'latest'` version block reads from `self._message.content` instead of `self._content`. The usage call reuses `get_anthropic_usage_attributes()` — the same function used by non-streaming `on_response()`. This works because `accumulate_event` produces a `Message` with final accurate usage.

## New import in `anthropic.py`

```python
from anthropic.lib.streaming._messages import accumulate_event
```

Also `ParsedMessage` for the type annotation on `self._message`. No new imports from `anthropic.types` are needed (no `MessageStartEvent`/`MessageDeltaEvent` isinstance checks).

## Possibly removed: `content_from_messages()` in `anthropic.py`

*(implements "The manual text accumulation is replaced by reading from the accumulated message")*

The helper that extracts text from `TextDelta`/`TextBlock` chunks is no longer called by `record_chunk()`. Check if any other code references it before removing.

## Not changed

- `get_anthropic_usage_attributes()` — now reused for both streaming and non-streaming (no modifications needed).
- `get_usage_attributes()` in `usage.py` — no changes needed.
- `on_response()` — non-streaming path, unchanged.
- `llm_provider.py` / `record_streaming()` — already passes through `get_attributes()` result.
- `types.py` / `StreamState` base class — no changes needed.
