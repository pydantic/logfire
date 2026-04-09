# Anthropic Streaming Usage Attributes

**Every Anthropic streaming span must have the same usage attributes as non-streaming spans: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.**
Context: Phase 3a (pydantic/logfire#1847) extracted `get_anthropic_usage_attributes(response)` in `anthropic.py` and refactored non-streaming `on_response()` to call it via the shared `get_usage_attributes()` from `usage.py`. Anthropic streaming `get_attributes()` currently ignores usage entirely — the streaming log span has no token counts, no cost, and no raw usage. This spec adds usage attributes to the `AnthropicMessageStreamState` streaming code path. Non-streaming Anthropic and all OpenAI paths are already handled.

**`AnthropicMessageStreamState.record_chunk()` must capture the `message_start` message and `message_delta` usage.** *(from "Every Anthropic streaming span")*
Context: Usage data arrives across two streaming events. `MessageStartEvent.message` is a full `Message` object with `model` and `usage` (type `Usage`, has `input_tokens`, `output_tokens`, cache fields). `MessageDeltaEvent.usage` is a `MessageDeltaUsage` with cumulative `output_tokens` and optional cumulative cache/input fields. Per the Anthropic SDK source, all `MessageDeltaUsage` fields are documented as "cumulative" — they replace (not add to) the corresponding `message_start` values. The `message_start.message` also carries `model`, needed for cost calculation. Currently `record_chunk()` only extracts text content.
It must additionally:
1. If the chunk is a `MessageStartEvent`, save `chunk.message` (the full `Message` object).
2. If the chunk is a `MessageDeltaEvent`, save `chunk.usage` (the `MessageDeltaUsage` object).
These are the only two event types that carry usage data. The type checks use `isinstance` against the SDK types, consistent with existing `isinstance` checks in `content_from_messages()`.

**`get_attributes()` calls `get_usage_attributes()` with tokens derived from the accumulated events.** *(from "AnthropicMessageStreamState.record_chunk() must capture")*
When both `message` and `message_delta_usage` are available:
- `input_tokens`: from `message.usage` with cache adjustment — `usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)` — identical to the non-streaming `get_anthropic_usage_attributes()`.
- `output_tokens`: from `message_delta_usage.output_tokens` (cumulative final value, replaces the `message_start` output count).
- `response`: the `message` from `message_start` — passed to `get_usage_attributes()` for cost calculation. `genai_prices.extract_usage(response.model_dump())` will find the `model` field on the `Message` object.
- `usage`: the `message.usage` object — used for `gen_ai.usage.raw` via `usage.model_dump(exclude_none=True)`.
When `message` is `None` (no `message_start` was received), no usage attributes are set.

**`gen_ai.usage.raw` uses the `message_start` usage object, not a synthetic merge.** *(from "get_attributes() calls get_usage_attributes()")*
The raw dict comes from `message.usage.model_dump(exclude_none=True)`, which is the `Usage` object from `message_start`. This preserves the full provider breakdown: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, etc. The `message_delta` usage is NOT merged into this dict — it's a different type (`MessageDeltaUsage`), and merging would create a synthetic object that doesn't match any real API response. The `output_tokens` in the raw dict may differ from `gen_ai.usage.output_tokens` (which uses the final `message_delta` value) — this is acceptable because `gen_ai.usage.raw` represents the raw provider data as received, while the flat attributes represent computed final values.

**The `get_anthropic_usage_attributes()` function is NOT reused for streaming.** *(from "get_attributes() calls get_usage_attributes()")*
That function takes a single response object with `response.usage` and reads everything from it. For streaming, input and output tokens come from different events, and the response object (`message_start.message`) may have stale `output_tokens`. Calling `get_usage_attributes()` directly (the shared low-level function) with the correct pre-computed values is cleaner than trying to mutate the message or create a synthetic wrapper. Context: This parallels OpenAI's streaming approach — `OpenaiChatCompletionStreamState.get_attributes()` calls `get_openai_usage_attributes(final_completion)` only because OpenAI's SDK reconstructs a complete object; Anthropic's doesn't.

**No try/except around the usage call in `get_attributes()`.** *(from "get_attributes() calls get_usage_attributes()")*
`get_usage_attributes()` has fine-grained internal error isolation (tokens, raw, and cost each fail independently). In the streaming path, `get_attributes()` is called inside `record_streaming()` which creates a log span — errors propagate but don't crash the user's code. Adding a broad `try/except` would hide real bugs. This matches the non-streaming approach and is consistent with phases 1–3a.

**Usage attributes are set regardless of semconv version.** *(from "Every Anthropic streaming span", "Existing streaming behavior")*
Context: The streaming code has version branching (`SemconvVersion`) — version 1 sets `response_data`, `'latest'` sets `OUTPUT_MESSAGES`. Usage attributes are set unconditionally, outside version-specific branches. This matches the non-streaming pattern established in phase 3a and the OpenAI streaming pattern from phase 2.

**Existing streaming behavior (response_data, output messages, duration) must not change.** *(from "Every Anthropic streaming span")*
This is additive — new usage attributes are added to the dict returned by `get_attributes()`. Context: The `response_data` dict (version 1) continues to contain `combined_chunk_content` and `chunk_count`. The `gen_ai.output.messages` (latest version) continues to contain the reconstructed assistant message. No existing attributes are modified. Existing streaming tests will gain the new usage attributes in their snapshots; Bedrock streaming tests follow the same pattern.
