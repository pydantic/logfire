# OpenAI Streaming Usage Attributes

**Code-level architecture is in [code-spec](code-spec.md).**

**Every OpenAI streaming span must have the same usage attributes as non-streaming spans: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.**
Context: Phase 1 (pydantic/logfire#1843) extracted usage logic into `get_usage_attributes()` in `usage.py` and refactored non-streaming `on_response()` to call it. Streaming `get_attributes()` methods currently ignore usage entirely. This spec adds usage attributes to the two OpenAI streaming code paths: chat completions and Responses API. Anthropic streaming is out of scope (separate spec).

**The OpenAI SDK already reconstructs usage from stream chunks — we just need to read it.** *(from "Every OpenAI streaming span")*
`OpenaiChatCompletionStreamState` wraps the SDK's `ChatCompletionStreamState`, which reconstructs a `current_completion_snapshot` (a full `ChatCompletion` object) from chunks. `OpenaiResponsesStreamState` wraps the SDK's `ResponseStreamState`, which reconstructs a `_completed_response` (a full `Response` object). Both reconstructed objects carry usage when the stream includes it. No new chunk parsing is needed.

**Usage may be None in streaming responses.** *(from "The OpenAI SDK already reconstructs usage")*
For chat completions, usage is only present when the caller passes `stream_options={"include_usage": True}`. For Responses API, usage is always present in the `response.completed` event. When usage is None, the usage attributes are simply omitted — the same behavior as non-streaming when a response has no usage.

**Each streaming state's `get_attributes()` calls `get_usage_attributes()` with the same parameters as the corresponding non-streaming `on_response()` path.** *(from "Every OpenAI streaming span", "The OpenAI SDK already reconstructs usage")*
Chat completions streaming uses `api_flavor='chat'`; Responses streaming uses `api_flavor='responses'`. Both use `provider_id='openai'`. Token field extraction uses the same `getattr` fallback pattern as `on_response()`.

**The reconstructed response object serves as the `response` parameter to `get_usage_attributes()`.** *(from "Each streaming state's `get_attributes()` calls `get_usage_attributes()`")*
For chat completions, `self._stream_state.current_completion_snapshot` is a `ChatCompletion` — the same type `on_response()` handles. For Responses, `get_response_data()` returns `self._state._completed_response`, a `Response` — same type as non-streaming. Both have `model_dump()` for cost calculation via `genai_prices`, and `.usage` for raw usage.

**Errors in usage extraction must not break streaming attribute collection.** *(from "Each streaming state's `get_attributes()` calls `get_usage_attributes()`")*
`get_usage_attributes()` already handles internal error isolation (tokens, raw usage, and cost fail independently). The `get_attributes()` call sites should catch any error from usage extraction (e.g., `current_completion_snapshot` raising `AssertionError` when there's no snapshot) so that other attributes (output messages, response_data, events) are still set.

**Existing streaming behavior (response_data, output messages, events) must not change.** *(from "Every OpenAI streaming span")*
This is additive — new attributes are added alongside existing ones. The `response_data` dict in version 1 chat completions streaming already includes `'usage': <usage_or_None>` and must continue to do so. The new semconv attributes are separate.

**Existing tests with VCR cassettes will show new usage attributes in snapshots.** *(from "Existing streaming behavior must not change")*
Tests that use `stream_options={"include_usage": True}` (e.g., `test_sync_chat_tool_call_stream`) will gain `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.raw`, and potentially `operation.cost` in their streaming log span snapshots. Tests without `include_usage` will show no change (usage remains None). The Responses streaming test (`test_responses_stream`) will gain usage attributes since the cassette's `response.completed` event already includes usage.
