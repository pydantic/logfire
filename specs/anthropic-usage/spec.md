# Anthropic Usage Attributes

**Every Anthropic span — streaming and non-streaming — must have the same four usage attributes: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.**
Context: Phase 1 (pydantic/logfire#1843) extracted shared usage logic into `get_usage_attributes()` in `usage.py`. Phase 2 (pydantic/logfire#1846) added these attributes to OpenAI streaming spans via `get_openai_usage_attributes()`. Anthropic non-streaming `on_response()` currently sets `input_tokens`, `output_tokens`, and `operation.cost` inline, but is missing `gen_ai.usage.raw`. Anthropic streaming sets none of the four. This spec brings both paths into parity.

**The Anthropic usage extraction logic must not be duplicated between non-streaming and streaming code paths.** *(from "Every Anthropic span")*
The same pattern as OpenAI: a single shared function in `anthropic.py` that, given a response-like object, extracts tokens (with cache adjustment), builds `USAGE_RAW`, and delegates to `get_usage_attributes()` for cost. Both `on_response()` and `AnthropicMessageStreamState.get_attributes()` call this function.

**Anthropic's `input_tokens` field only counts uncached tokens; `gen_ai.usage.input_tokens` must be the total.** *(from "Every Anthropic span")*
Per OTel GenAI semconv, `gen_ai.usage.input_tokens` should reflect the total input tokens processed. Anthropic's `Usage.input_tokens` excludes cached tokens. The total is `input_tokens + (cache_read_input_tokens or 0) + (cache_creation_input_tokens or 0)`. This logic currently lives inline in `on_response()` (lines 342–351 of `anthropic.py`) and must move into the shared function.

**`gen_ai.usage.raw` preserves the full provider usage object, including cache token breakdown.** *(from "Every Anthropic span", "Anthropic's input_tokens field only counts uncached tokens")*
The raw dict (from `usage.model_dump(exclude_none=True)`) retains `cache_read_input_tokens`, `cache_creation_input_tokens`, and any other provider-specific fields. This is the whole point of `USAGE_RAW` — users can see the cache breakdown that the flat `input_tokens` total loses. Context: `get_usage_attributes()` already handles `USAGE_RAW` serialization; the shared function just needs to pass the usage object through.

**Anthropic streaming delivers usage across two events: `message_start` and `message_delta`.** *(from "The Anthropic usage extraction logic must not be duplicated")*
`message_start` contains a full `Message` object with `Usage` (model, input_tokens, cache tokens, and an initial `output_tokens` — typically 0). `message_delta` contains `MessageDeltaUsage` with the final cumulative `output_tokens` (and possibly delta cache tokens). `message_stop` has no usage. The stream state must capture both to produce accurate final usage. Context: This differs from OpenAI, where the SDK reconstructs a full response object (`ChatCompletion` or `Response`) that can be passed directly to the shared function. Anthropic's SDK does not reconstruct a final `Message` from stream events — we must assemble the final usage ourselves.

**The stream state captures the `Message` from `message_start` and the `MessageDeltaUsage` from `message_delta`.** *(from "Anthropic streaming delivers usage across two events")*
`record_chunk()` already processes every stream event. It now additionally captures these two objects when present. Context: `MessageStartEvent` has a `.message` attribute (a `Message` with model, id, usage, etc.). `RawMessageDeltaEvent` has a `.usage` attribute (a `MessageDeltaUsage`).

**For cost calculation, the stream state constructs a merged response dict rather than passing the `message_start` Message directly.** *(from "The stream state captures the Message from message_start", "Anthropic streaming delivers usage across two events")*
`get_usage_attributes()` calls `response.model_dump()` and passes it to `genai_prices.extract_usage()`. If we pass the `message_start` Message directly, its usage has the initial `output_tokens` (typically 0), producing incorrect cost. Instead, the stream state builds the correct usage by starting with the `message_start` Message's `model_dump()` and overriding usage fields from `message_delta`. This merged dict is wrapped in a simple object with a `model_dump()` method so it satisfies `get_usage_attributes()`'s interface. Context: This is the same `response.model_dump()` overhead as pydantic/logfire#1844 for OpenAI. No mitigation here — that issue tracks it separately.

**The shared function handles a `Message`, `BetaMessage`, or the merged streaming wrapper identically.** *(from "The Anthropic usage extraction logic must not be duplicated", "For cost calculation, the stream state constructs a merged response dict")*
The function uses `getattr` for `usage` and cache token fields, so it works with any object that has the right attributes. For non-streaming it receives a `Message`/`BetaMessage` directly. For streaming it receives the merged wrapper. The cache adjustment and `get_usage_attributes()` delegation are the same in both cases.

**`on_response()` is refactored to use the shared function, adding `gen_ai.usage.raw` to non-streaming spans.** *(from "The Anthropic usage extraction logic must not be duplicated")*
The inline token-setting and cost calculation blocks (lines 342–367 of `anthropic.py`) are replaced by a single call to the shared function plus `span.set_attributes()`. This is a behavioral change: non-streaming spans gain the `gen_ai.usage.raw` attribute they currently lack. The `usage` variable used for `response_data` in version 1 (line 332) remains — it's separate from the new shared function.

**No broad try/except around usage extraction at call sites.** *(from "The Anthropic usage extraction logic must not be duplicated")*
Same principle as OpenAI (phase 2): `get_usage_attributes()` already has fine-grained error isolation internally. Wrapping the entire usage call in a silent `try/except` at the call site would hide real bugs. In `on_response()`, errors surface via the existing `@handle_internal_errors` decorator. In streaming `get_attributes()`, errors are not currently decorated with `handle_internal_errors`, but that's pre-existing — the usage code should not add its own silent suppression.

**Usage attributes are set regardless of semconv version.** *(from "Every Anthropic span")*
Context: The Anthropic code has version branching (`SemconvVersion`) — version 1 sets `response_data`, `'latest'` sets `OUTPUT_MESSAGES`. Usage attributes are set unconditionally, outside version-specific branches. This matches the pattern established in phases 1 and 2.

**Existing streaming behavior (response_data, output messages) must not change.** *(from "Every Anthropic span")*
This is additive — new attributes are added alongside existing ones. The version 1 `response_data` dict (combined_chunk_content, chunk_count) continues to be set. The `OUTPUT_MESSAGES` attribute continues to be set for `'latest'` version.

**Existing tests will show new attributes in snapshots.** *(from "Existing streaming behavior must not change", "`on_response()` is refactored to use the shared function")*
Non-streaming tests gain `gen_ai.usage.raw` in their snapshots (this was previously missing). Streaming tests gain all four usage attributes in their streaming log span snapshots — the mock data already includes `MessageStartEvent` with usage and `MessageDeltaEvent` with `output_tokens`.

**Anthropic Bedrock uses the same `on_response()` and stream state.** *(from "Every Anthropic span")*
Context: `AnthropicBedrock` and `AsyncAnthropicBedrock` clients route through the same `get_endpoint_config()` and `on_response()` as standard Anthropic clients. The shared function works identically for Bedrock — it doesn't inspect the client type, only the response object.
