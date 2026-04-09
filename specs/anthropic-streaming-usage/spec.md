# Anthropic Streaming Usage Attributes

**Code-level architecture is in [code-spec](code-spec.md).**

**Every Anthropic streaming span must have the same usage attributes as non-streaming spans: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.**
Context: Non-streaming `on_response()` already uses `get_anthropic_usage_attributes()` (in `anthropic.py`) which delegates to the shared `get_usage_attributes()` (in `usage.py`). Anthropic streaming `get_attributes()` currently ignores usage entirely — the streaming log span has no token counts, no cost, and no raw usage. Non-streaming Anthropic and all OpenAI paths are already handled.

**`AnthropicMessageStreamState.record_chunk()` must capture the `message_start` message and `message_delta` usage.** *(from "Every Anthropic streaming span")*
In addition to extracting text content, `record_chunk()` must:
1. If the chunk is a `MessageStartEvent`, save `chunk.message` (the full `Message` object).
2. If the chunk is a `MessageDeltaEvent`, save `chunk.usage` (the `MessageDeltaUsage` object).
These are the only two event types that carry usage data. The type checks use `isinstance` against the SDK types, consistent with existing `isinstance` checks in `content_from_messages()`.
Context: `MessageStartEvent.message` is a full `Message` object with `model` and `usage` (type `Usage`, has `input_tokens`, `output_tokens`, cache fields). `MessageDeltaEvent.usage` is a `MessageDeltaUsage` with cumulative `output_tokens` and optional cumulative cache/input fields. Per the Anthropic SDK source, all `MessageDeltaUsage` fields are documented as "cumulative" — they replace (not add to) the corresponding `message_start` values. The `message_start.message` also carries `model`, needed for cost calculation.

**`get_attributes()` calls `get_usage_attributes()` with tokens derived from the accumulated events.** *(from "AnthropicMessageStreamState.record_chunk() must capture")*
Computes final token counts from the captured events and delegates to the shared `get_usage_attributes()`. When `message` is `None` (no `message_start` was received), no usage attributes are set. When both `message` and `message_delta_usage` are available:
- `input_tokens`: from `message.usage` with cache adjustment — `usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)` — identical to the non-streaming `get_anthropic_usage_attributes()`.
- `output_tokens`: from `message_delta_usage.output_tokens` (cumulative final value, replaces the `message_start` output count).
- `response`: the `message` from `message_start` — passed to `get_usage_attributes()` for cost calculation. Context: `genai_prices.extract_usage(response.model_dump())` will find the `model` field on the `Message` object.
- `usage`: the `message.usage` object — used for `gen_ai.usage.raw` via `usage.model_dump(exclude_none=True)`.

**`gen_ai.usage.raw` uses the `message_start` usage object, not a synthetic merge.** *(from "AnthropicMessageStreamState.record_chunk() must capture", "get_attributes() calls get_usage_attributes()")*
The raw dict comes from `message.usage.model_dump(exclude_none=True)`, which is the `Usage` object from `message_start`. This preserves the full provider breakdown: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, etc. The `message_delta` usage is NOT merged into this dict — it's a different type (`MessageDeltaUsage`), and merging would create a synthetic object that doesn't match any real API response. The `output_tokens` in the raw dict may differ from `gen_ai.usage.output_tokens` (which uses the final `message_delta` value) — this is acceptable because `gen_ai.usage.raw` represents the raw provider data as received, while the flat attributes represent computed final values.

**The `get_anthropic_usage_attributes()` function is NOT reused for streaming.** *(from "get_attributes() calls get_usage_attributes()")*
That function takes a single response object with `response.usage` and reads everything from it. For streaming, input and output tokens come from different events, and the response object (`message_start.message`) may have stale `output_tokens`. Calling `get_usage_attributes()` directly (the shared low-level function) with the correct pre-computed values is cleaner than trying to mutate the message or create a synthetic wrapper. Context: OpenAI's streaming approach calls `get_openai_usage_attributes(final_completion)` because the OpenAI SDK reconstructs a complete response object from stream chunks; Anthropic's SDK doesn't do this.

**No try/except around the usage call in `get_attributes()`.** *(from "get_attributes() calls get_usage_attributes()")*
`get_usage_attributes()` has fine-grained internal error isolation (tokens, raw, and cost each fail independently). In the streaming path, `get_attributes()` is called inside `record_streaming()` which creates a log span — errors propagate but don't crash the user's code. Adding a broad `try/except` would hide real bugs. This matches the non-streaming approach and the OpenAI streaming approach.

**Existing streaming behavior (response_data, output messages, duration) must not change.** *(from "Every Anthropic streaming span")*
This is purely additive — new usage attributes are added alongside existing ones in the dict returned by `get_attributes()`. Existing streaming tests will gain the new usage attributes in their snapshots; Bedrock streaming tests follow the same pattern.

**Usage attributes are set regardless of semconv version.** *(from "Every Anthropic streaming span")*
This matches the existing non-streaming pattern (where `on_response()` sets usage attributes outside version-specific branches) and the OpenAI streaming pattern. Context: The streaming code has version branching (`SemconvVersion`) — version 1 sets `response_data`, `'latest'` sets `OUTPUT_MESSAGES`. Usage attributes are set unconditionally, outside version-specific branches.
