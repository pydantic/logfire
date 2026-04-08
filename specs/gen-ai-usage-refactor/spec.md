# Refactor GenAI Usage Attributes into Shared Code

**Code-level architecture is in [code-spec](code-spec.md).**

**The long-term goal is for every GenAI span to have four usage attributes: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.**
Context: `input_tokens` and `output_tokens` are standard OTel GenAI semconv attributes. `operation.cost` is the dollar cost computed via the optional `genai_prices` library. `gen_ai.usage.raw` is the full provider usage object as a dict, preserving provider-specific detail (cached tokens, reasoning tokens) that the flat counts lose. Today, non-streaming paths set most of these but streaming paths set none.

**This spec covers only the refactoring step: extracting shared usage logic from OpenAI's `on_response()` into reusable code.** *(from "The long-term goal")*
No new attributes are added to streaming spans. The refactoring produces shared code that future work (OpenAI streaming, Anthropic) will call into, but this PR only restructures existing OpenAI non-streaming code. The observable behavior should not change.

**The usage attribute logic must not be duplicated across providers or streaming modes.** *(from "The long-term goal", "This spec covers only the refactoring step")*
There are 3 API surfaces (OpenAI chat completions, OpenAI Responses, Anthropic Messages) x 2 modes (streaming, non-streaming) that eventually need these attributes. Today the logic is duplicated between `openai.py` and `anthropic.py` `on_response()` functions, and adding streaming would triple it. A shared function avoids this.

**Each API surface has two provider-specific concerns: token extraction and `genai_prices` parameters.** *(from "The usage attribute logic must not be duplicated")*
Token field names differ per API surface: OpenAI chat uses `prompt_tokens`/`completion_tokens`, OpenAI Responses uses `input_tokens`/`output_tokens`, Anthropic needs `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. For cost, `genai_prices` needs `provider_id` (`'openai'`/`'anthropic'`) and for OpenAI also `api_flavor` (`'chat'`/`'responses'`). Callers handle these differences; the shared code handles everything else.

**Everything else about setting usage attributes is the same and belongs in shared code.** *(from "Each API surface has two provider-specific concerns")*
Given the extracted token counts, the usage object, and the pricing parameters, the shared code: sets `INPUT_TOKENS` and `OUTPUT_TOKENS`, sets `USAGE_RAW` via `model_dump(exclude_none=True)`, and computes `operation.cost` via `genai_prices` (try/except since it's optional).

**`genai_prices` is an optional dependency.** *(from "Everything else about setting usage attributes")*
It must not be imported at module level. Cost calculation uses it when available; failures are silently caught. Token extraction cannot depend on it.

**Usage attributes are set regardless of semconv version.** *(from "The long-term goal")*
The version system (`SemconvVersion`) controls other attribute formatting. Usage attributes are small values where duplication across versions is intentional.

**Existing `response_data.usage` in version 1 must not be removed.** *(from "Usage attributes are set regardless of semconv version")*
This is existing behavior in OpenAI non-streaming. The new shared code adds attributes alongside `response_data`, not instead of it.
