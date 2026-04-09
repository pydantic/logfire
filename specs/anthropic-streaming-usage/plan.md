# Implementation Plan: Anthropic Streaming Usage Attributes

Implements `specs/anthropic-streaming-usage/spec.md` and `code-spec.md`.

## Commit 1: Add `accumulate_event` import and replace `_content` with `_message` in `__init__`

**File: `logfire/_internal/integrations/llm_providers/anthropic.py`**

1. Add import: `from anthropic.lib.streaming._messages import accumulate_event, ParsedMessage`
2. In `AnthropicMessageStreamState.__init__`: replace `self._content: list[str] = []` with `self._message: ParsedMessage[object] | None = None`

This is a mechanical change — the new state variable replaces the old one. Nothing will work yet (methods still reference `self._content`), but it's the foundation.

## Commit 2: Replace `record_chunk()` to use `accumulate_event`

**File: `logfire/_internal/integrations/llm_providers/anthropic.py`**

Replace the body of `record_chunk()`:

```python
def record_chunk(self, chunk: anthropic.types.MessageStreamEvent) -> None:
    self._message = accumulate_event(event=chunk, current_snapshot=self._message)
```

This replaces the manual `content_from_messages()` extraction. Each chunk updates the accumulated message snapshot.

## Commit 3: Update `get_response_data()` to read from `self._message`

**File: `logfire/_internal/integrations/llm_providers/anthropic.py`**

`get_response_data()` currently returns `{'combined_chunk_content': ''.join(self._content), 'chunk_count': len(self._content)}`.

Replace to extract from `self._message.content`:
- Iterate `self._message.content` blocks, collect text from `TextBlock` instances
- `combined_chunk_content` = joined text from all text blocks
- `chunk_count` = number of text blocks

Note: The old `chunk_count` counted text deltas (2 for "The answer" + " is secret"), while `accumulate_event` merges them into content blocks (1 text block). `chunk_count` is a v1 response_data field — its semantics change slightly but the important data (`combined_chunk_content`) stays the same. Snapshots will update.

## Commit 4: Update `get_attributes()` to read from `self._message` and add usage

**File: `logfire/_internal/integrations/llm_providers/anthropic.py`**

Two changes in `get_attributes()`:

1. **`'latest'` branch**: Change `if 'latest' in versions and self._content:` to read from `self._message.content` instead. Extract text from content blocks (same as `get_response_data` but building `OutputMessage`/`TextPart`).

2. **Usage attributes** (outside version branches): Add after the version-specific blocks:
   ```python
   if self._message is not None:
       result.update(get_anthropic_usage_attributes(self._message))
   ```

This is the key change — streaming spans now get `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.

## Commit 5: Remove `content_from_messages()` if unused

**File: `logfire/_internal/integrations/llm_providers/anthropic.py`**

`content_from_messages()` (lines 270-275) is no longer called by `record_chunk()`. Grep confirms it's only referenced in `anthropic.py` itself. Remove it.

## Commit 6: Update test snapshots

**File: `tests/otel_integrations/test_anthropic.py`**

Run affected streaming tests with `--inline-snapshot=fix` to update snapshots:

```
uv run pytest tests/otel_integrations/test_anthropic.py -k "stream" --inline-snapshot=fix
```

Expected snapshot changes on the streaming log span (second span):
- New attributes: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.raw`, `operation.cost`
- `response_data.chunk_count` may change (text blocks vs text deltas)
- `logfire.json_schema.properties` gains entries for the new usage attributes

Affected tests:
- `test_sync_messages_stream` (v1+latest, mock transport)
- `test_async_messages_stream` (v1+latest, mock transport)
- `test_sync_messages_stream_version_latest` (VCR)
- `test_sync_messages_stream_version_v1_only` (VCR)
- `test_sync_messages_beta_stream` (VCR)

## Commit 7: Add unit test for streaming usage attributes

**File: `tests/otel_integrations/test_anthropic.py`**

Add a focused test that verifies the streaming span contains the expected usage attributes. This can use the existing mock transport (which provides `Usage(input_tokens=25, output_tokens=25)` at `message_start` and `MessageDeltaUsage(output_tokens=55)` at `message_delta`). The test should verify:
- `gen_ai.usage.input_tokens` = 25 (no cache tokens in mock)
- `gen_ai.usage.output_tokens` = 55 (final from message_delta)
- `gen_ai.usage.raw` contains the full usage dict
- `operation.cost` is present (exact value depends on genai_prices)

## Verification

After all commits, run:
```
uv run pytest tests/otel_integrations/test_anthropic.py -x
make typecheck
```
