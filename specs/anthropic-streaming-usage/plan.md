# Implementation Plan: Anthropic Streaming Usage Attributes

Implements `specs/anthropic-streaming-usage/spec.md` and `code-spec.md`.

## Commit 1: Rewrite `AnthropicMessageStreamState` to use `accumulate_event`, remove `content_from_messages()`

**File: `logfire/_internal/integrations/llm_providers/anthropic.py`**

All code changes in one commit — these can't be split because changing `__init__` breaks every method that references `self._content`.

1. **Add import**: `from anthropic.lib.streaming._messages import accumulate_event` and `from anthropic.types.parsed_message import ParsedMessage` (pyright requires importing `ParsedMessage` from this public re-export, not from `_messages`).

2. **`__init__`**: Replace `self._content: list[str] = []` with `self._message: ParsedMessage[object] | None = None`.

3. **`record_chunk()`**: Replace body with:
   ```python
   self._message = accumulate_event(event=chunk, current_snapshot=self._message)
   ```

4. **`get_response_data()`**: Read from `self._message.content` blocks instead of `self._content`:
   ```python
   def get_response_data(self) -> Any:
       if self._message is None:
           return {'combined_chunk_content': '', 'chunk_count': 0}
       texts = [block.text for block in self._message.content if isinstance(block, (TextBlock, BetaTextBlock))]
       return {'combined_chunk_content': ''.join(texts), 'chunk_count': len(texts)}
   ```
   Note: `chunk_count` semantics change (text blocks vs text deltas). Snapshots will update.

5. **`get_attributes()`**: Two changes:
   - `'latest'` branch: read text from `self._message.content` blocks instead of `self._content`
   - After version-specific blocks, add usage attributes:
     ```python
     if self._message is not None:
         result.update(get_anthropic_usage_attributes(self._message))
     ```

6. **Remove `content_from_messages()`** — no longer called anywhere.

## Commit 2: Update test snapshots

**File: `tests/otel_integrations/test_anthropic.py`**

```
uv run pytest tests/otel_integrations/test_anthropic.py -k "stream" --inline-snapshot=fix
```

Expected snapshot changes on the streaming log span:
- New attributes: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.raw`, `operation.cost`
- `response_data.chunk_count` changes (text blocks vs text deltas)
- `logfire.json_schema.properties` gains entries for the new usage attributes

Affected tests:
- `test_sync_messages_stream` (v1+latest, mock transport)
- `test_async_messages_stream` (v1+latest, mock transport)
- `test_sync_messages_stream_version_latest` (VCR)
- `test_sync_messages_stream_version_v1_only` (VCR)
- `test_sync_messages_beta_stream` (VCR)

## Commit 3: Add unit test for streaming usage attributes

**File: `tests/otel_integrations/test_anthropic.py`**

Add a focused test verifying the streaming span contains expected usage attributes. Uses the existing mock transport (`Usage(input_tokens=25, output_tokens=25)` at `message_start`, `MessageDeltaUsage(output_tokens=55)` at `message_delta`). Verify:
- `gen_ai.usage.input_tokens` = 25 (no cache tokens in mock)
- `gen_ai.usage.output_tokens` = 55 (final from message_delta)
- `gen_ai.usage.raw` contains the full usage dict
- `operation.cost` is present

## Verification

After all commits:
```
uv run pytest tests/otel_integrations/test_anthropic.py -x
make typecheck
```
