# OpenAI Streaming Usage Attributes

**Code-level architecture is in [code-spec](code-spec.md).**

**Every OpenAI streaming span must have the same usage attributes as non-streaming spans: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.**
Context: Phase 1 (pydantic/logfire#1843) extracted usage logic into `get_usage_attributes()` in `usage.py` and refactored non-streaming `on_response()` to call it. Streaming `get_attributes()` methods currently ignore usage entirely. This spec adds usage attributes to the two OpenAI streaming code paths: chat completions and Responses API. The OpenAI Agents integration (`openai_agents.py`) has its own code path and is out of scope. Legacy text completions (`OpenaiCompletionStreamState`) are out of scope. Anthropic streaming is out of scope (separate spec).

**The OpenAI SDK already reconstructs usage from stream chunks — we just need to read it.** *(from "Every OpenAI streaming span")*
`OpenaiChatCompletionStreamState` wraps the SDK's `ChatCompletionStreamState`, which reconstructs a `current_completion_snapshot` (a full `ChatCompletion` object) from chunks. `OpenaiResponsesStreamState` wraps the SDK's `ResponseStreamState`, which reconstructs a `_completed_response` (a full `Response` object). Both reconstructed objects carry usage when the stream includes it. No new chunk parsing is needed.

**Usage may be None in streaming responses.** *(from "The OpenAI SDK already reconstructs usage")*
For chat completions, usage is only present when the caller passes `stream_options={"include_usage": True}`. For Responses API, usage is always present in the `response.completed` event. When usage is None, the usage attributes are simply omitted — the same behavior as non-streaming when a response has no usage.

**The usage extraction logic (getting usage from a response, extracting tokens, determining api_flavor, calling `get_usage_attributes()`) must not be duplicated across OpenAI code paths.** *(from "Every OpenAI streaming span")*
Today, `on_response()` has this logic inline (lines 595–609 of `openai.py`). Adding streaming would duplicate it twice more. Instead, a single shared function handles all OpenAI response objects — streaming and non-streaming, chat and Responses and embeddings. Given any OpenAI response object, the steps are always the same: get `.usage`, extract token counts via `getattr` fallback, determine `api_flavor` from the response type, call `get_usage_attributes()`. The only thing that varies is where the response object comes from, which the caller provides.

**In the streaming path, usage attributes go on the log span created by `record_streaming()`.** *(from "Every OpenAI streaming span")*
Context: `record_streaming()` in `llm_provider.py` calls `stream_state.get_attributes(span_data)` and passes the result as kwargs to `logfire_llm.info()`, creating a log span. This differs from non-streaming where `on_response()` calls `span.set_attributes()` on the main span. No changes to `record_streaming()` are needed — it already passes through whatever `get_attributes()` returns.

**The reconstructed response object is the same type as non-streaming, so the shared function works for both.** *(from "The usage extraction logic must not be duplicated", "The OpenAI SDK already reconstructs usage")*
For chat completions, `current_completion_snapshot` is a `ChatCompletion`. For Responses, `get_response_data()` returns a `Response`. These are the same types `on_response()` handles. The `isinstance` checks for `api_flavor` determination work unchanged.

**No broad try/except around usage extraction at call sites.** *(from "The usage extraction logic must not be duplicated")*
`get_usage_attributes()` already has fine-grained error isolation internally (tokens, raw usage, and cost each fail independently). Wrapping the entire usage call in a silent `try/except Exception: pass` at the call site would hide real bugs (e.g., a broken `getattr` chain, a wrong type). Errors in the shared function's callers should surface normally via `handle_internal_errors` (which already decorates `on_response()`). In streaming `get_attributes()`, errors are not currently decorated with `handle_internal_errors`, but that's pre-existing — the usage code should not add its own silent suppression.

**Usage attributes are set regardless of semconv version.** *(from "Every OpenAI streaming span")*
Context: The streaming code has version branching (`SemconvVersion`) — version 1 sets `response_data`, `'latest'` sets `OUTPUT_MESSAGES`. Usage attributes are small scalar/dict values that should be set unconditionally, outside version-specific branches. This matches the non-streaming behavior in `on_response()`.

**`genai_prices` is an optional dependency; cost failures are silently caught.** *(from "The usage extraction logic must not be duplicated")*
This is inherited from `get_usage_attributes()` and requires no new code — the shared function already handles it. Restated here because it's a key architectural constraint: token extraction must never depend on `genai_prices`, and cost errors (missing library, unsupported model) must not surface to users.

**Existing streaming behavior (response_data, output messages, events) must not change.** *(from "Every OpenAI streaming span")*
This is additive — new attributes are added alongside existing ones. The `response_data` dict in version 1 chat completions streaming already includes `'usage': <usage_or_None>` and must continue to do so. The new semconv attributes are separate.

**Known issue: `response.model_dump()` for cost calculation serializes the full response.** *(from "The usage extraction logic must not be duplicated")*
For streaming, this means serializing the full reconstructed response object. This is the same issue as pydantic/logfire#1844 (filed during phase 1 for embeddings). No mitigation in this spec — the issue tracks it separately.

**Existing tests with VCR cassettes will show new usage attributes in snapshots.** *(from "Existing streaming behavior must not change")*
Tests that use `stream_options={"include_usage": True}` (e.g., `test_sync_chat_tool_call_stream`) will gain `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.raw`, and potentially `operation.cost` in their streaming log span snapshots. Tests without `include_usage` will show no change (usage remains None). The Responses streaming test (`test_responses_stream`) will gain usage attributes since the cassette's `response.completed` event already includes usage.
