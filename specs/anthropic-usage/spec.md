# Anthropic Non-Streaming Usage Refactor

**Anthropic non-streaming `on_response()` must use the shared `get_usage_attributes()`, adding `gen_ai.usage.raw` which is currently missing.**
Context: Phase 1 (pydantic/logfire#1843) extracted shared usage logic into `get_usage_attributes()` in `usage.py`. Phase 2 (pydantic/logfire#1846) added usage attributes to OpenAI streaming spans via `get_openai_usage_attributes()` and refactored OpenAI's `on_response()` to use it. Anthropic's `on_response()` still has inline token-setting (lines 342–351) and cost calculation (lines 357–367) that predate the shared function. It sets `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, and `operation.cost`, but not `gen_ai.usage.raw`. This spec refactors it to use the shared code, bringing it into parity with OpenAI and adding the missing attribute. Anthropic streaming is out of scope (separate spec).

**A shared `get_anthropic_usage_attributes()` function in `anthropic.py` encapsulates the Anthropic-specific extraction, parallel to `get_openai_usage_attributes()`.** *(from "Anthropic non-streaming on_response() must use the shared get_usage_attributes()")*
Given a `Message` or `BetaMessage`, it extracts usage with cache adjustment, determines token counts, and delegates to `get_usage_attributes()`. This lives in `anthropic.py` (not `usage.py`) because the cache token adjustment and `isinstance` checks are Anthropic-specific — same reasoning as OpenAI's function living in `openai.py`.

**Anthropic's `input_tokens` field only counts uncached tokens; `gen_ai.usage.input_tokens` must be the total.** *(from "A shared get_anthropic_usage_attributes() function")*
Per OTel GenAI semconv, `gen_ai.usage.input_tokens` should reflect total input tokens processed. Anthropic's `Usage.input_tokens` excludes cached tokens. The total is `input_tokens + (cache_read_input_tokens or 0) + (cache_creation_input_tokens or 0)`. This logic currently lives inline in `on_response()` and moves into the shared function.

**`gen_ai.usage.raw` preserves the full provider usage object, including cache token breakdown.** *(from "Anthropic non-streaming on_response() must use the shared get_usage_attributes()", "Anthropic's input_tokens field only counts uncached tokens")*
The raw dict (from `usage.model_dump(exclude_none=True)`) retains `cache_read_input_tokens`, `cache_creation_input_tokens`, and any other provider-specific fields. Users can see the cache breakdown that the flat `input_tokens` total loses. Context: `get_usage_attributes()` already handles `USAGE_RAW` serialization; the shared function just needs to pass the usage object through.

**`on_response()` replaces inline usage logic with a call to the shared function.** *(from "A shared get_anthropic_usage_attributes() function")*
The inline token-setting block (lines 342–352) and cost calculation block (lines 357–367) are replaced by `span.set_attributes(get_anthropic_usage_attributes(response))`. This is a behavioral change: non-streaming spans gain `gen_ai.usage.raw`. The `response.usage` reference in the version 1 `response_data` dict (line 332) remains unchanged — it's separate from the usage attributes.

**No broad try/except around usage extraction at call sites.** *(from "A shared get_anthropic_usage_attributes() function")*
`get_usage_attributes()` already has fine-grained error isolation internally (tokens, raw usage, and cost each fail independently). In `on_response()`, errors surface via the existing `@handle_internal_errors` decorator.

**Usage attributes are set regardless of semconv version.** *(from "Anthropic non-streaming on_response() must use the shared get_usage_attributes()")*
Context: The Anthropic code has version branching (`SemconvVersion`) — version 1 sets `response_data`, `'latest'` sets `OUTPUT_MESSAGES`. Usage attributes are set unconditionally, outside version-specific branches. This matches the pattern established in phases 1 and 2.

**Existing non-streaming behavior (response_data, output messages, response model/id, finish reasons) must not change.** *(from "Anthropic non-streaming on_response() must use the shared get_usage_attributes()")*
This is additive — the only new attribute is `gen_ai.usage.raw`. Existing attributes continue to be set by `on_response()` as before.

**Existing tests will gain `gen_ai.usage.raw` in snapshots.** *(from "Existing non-streaming behavior must not change")*
Non-streaming tests that assert on span attributes will show the new `gen_ai.usage.raw` dict in their snapshots. No other snapshot changes are expected.

**Anthropic Bedrock uses the same `on_response()`.** *(from "Anthropic non-streaming on_response() must use the shared get_usage_attributes()")*
Context: `AnthropicBedrock` and `AsyncAnthropicBedrock` clients route through the same `on_response()` as standard Anthropic clients. The shared function works identically — it doesn't inspect the client type, only the response object.
