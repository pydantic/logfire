# Anthropic Streaming Usage Attributes — Code Spec

**This implements the prose spec in [spec](spec.md), which is the primary source of truth.**

## Modified: `AnthropicMessageStreamState.__init__()` in `anthropic.py`

*(implements "record_chunk() must capture the message_start message and message_delta usage")*

```python
def __init__(self):
    self._content: list[str] = []
    self._message: Message | None = None
    self._message_delta_usage: MessageDeltaUsage | None = None
```

Currently only has `self._content`. Add two fields to hold the captured event data.

## Modified: `AnthropicMessageStreamState.record_chunk()` in `anthropic.py`

*(implements "record_chunk() must capture the message_start message and message_delta usage")*

```python
def record_chunk(self, chunk: anthropic.types.MessageStreamEvent) -> None:
    content = content_from_messages(chunk)
    if content:
        self._content.append(content)
    if isinstance(chunk, MessageStartEvent):
        self._message = chunk.message
    elif isinstance(chunk, MessageDeltaEvent):
        self._message_delta_usage = chunk.usage
```

Adds `isinstance` checks after existing text extraction. `MessageStartEvent` and `MessageDeltaEvent` need to be imported from `anthropic.types`.

## Modified: `AnthropicMessageStreamState.get_attributes()` in `anthropic.py`

*(implements "get_attributes() calls get_usage_attributes()", "Usage attributes are set regardless of semconv version", "Existing streaming behavior must not change")*

```python
def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
    versions = self._versions
    result = dict(**span_data)
    if 1 in versions:
        result['response_data'] = self.get_response_data()
    if 'latest' in versions and self._content:
        combined = ''.join(self._content)
        result[OUTPUT_MESSAGES] = [
            OutputMessage(
                role='assistant',
                parts=[TextPart(type='text', content=combined)],
            )
        ]
    # Usage attributes — outside version-specific branches
    result.update(self._get_usage_attributes())
    return result
```

Existing version-specific blocks are unchanged. The new `result.update()` call is appended after them, unconditionally.

## New: `AnthropicMessageStreamState._get_usage_attributes()` in `anthropic.py`

*(implements "get_attributes() calls get_usage_attributes()", "gen_ai.usage.raw uses the message_start usage object", "The get_anthropic_usage_attributes() function is NOT reused")*

```python
def _get_usage_attributes(self) -> dict[str, Any]:
    """Compute usage attributes from accumulated streaming events."""
```

Private helper on the stream state class. Returns `{}` when `self._message` is `None`. When both `_message` and `_message_delta_usage` are available:
- Computes `input_tokens` from `self._message.usage` with cache adjustment (same formula as `get_anthropic_usage_attributes()`).
- Takes `output_tokens` from `self._message_delta_usage.output_tokens`.
- Calls `get_usage_attributes(self._message, self._message.usage, input_tokens, output_tokens, provider_id='anthropic')`.

Passes `self._message` as `response` (for cost calculation via `genai_prices`) and `self._message.usage` as `usage` (for `gen_ai.usage.raw`).

## New imports in `anthropic.py`

`MessageDeltaEvent` and `MessageStartEvent` from `anthropic.types`. These are needed for the `isinstance` checks in `record_chunk()`.

## Not changed

- `get_anthropic_usage_attributes()` — not reused for streaming; remains as-is for non-streaming.
- `get_usage_attributes()` in `usage.py` — no changes needed.
- `on_response()` — non-streaming path, unchanged.
- `llm_provider.py` / `record_streaming()` — already passes through `get_attributes()` result.
- `types.py` / `StreamState` base class — no changes needed.
