# Refactor GenAI Usage Attributes into Shared Code

**Code-level architecture is in [code-spec](code-spec.md).**

**The long-term goal is for every GenAI span to have four usage attributes: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `operation.cost`, and `gen_ai.usage.raw`.**
Context: `input_tokens` and `output_tokens` are standard OTel GenAI semconv attributes. `operation.cost` is the dollar cost computed via the optional `genai_prices` library. `gen_ai.usage.raw` is the full provider usage object as a dict, preserving provider-specific detail (cached tokens, reasoning tokens) that the flat counts lose. Today, non-streaming paths set most of these but streaming paths set none.

**This spec covers only the refactoring step: extracting shared usage logic from OpenAI's `on_response()` into reusable code.** *(from "The long-term goal")*
No new attributes are added to streaming spans. The refactoring produces shared code that future work (OpenAI streaming, Anthropic) will call into, but this PR only restructures existing OpenAI non-streaming code. The observable behavior should not change, with one exception: embeddings cost calculation is currently broken (see below) and gets fixed as a side effect.

**The usage attribute logic must not be duplicated across providers or streaming modes.** *(from "The long-term goal", "This spec covers only the refactoring step")*
There are multiple API surfaces (OpenAI chat completions, OpenAI Responses, OpenAI embeddings, Anthropic Messages) x 2 modes (streaming, non-streaming) that eventually need these attributes. Today the logic is duplicated between `openai.py` and `anthropic.py` `on_response()` functions, and adding streaming would triple it. A shared function avoids this.

**Each API surface has two provider-specific concerns: token extraction and `genai_prices` parameters.** *(from "The usage attribute logic must not be duplicated")*
Token field names differ per API surface: OpenAI chat uses `prompt_tokens`/`completion_tokens`, OpenAI Responses uses `input_tokens`/`output_tokens`, Anthropic needs `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. The existing fallback pattern (`getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', None))`) works safely across all OpenAI API surfaces and should be preserved. For cost, `genai_prices` needs the full response object (it extracts both model and usage internally), `provider_id` (`'openai'`/`'anthropic'`), and for OpenAI also `api_flavor` (`'chat'`/`'responses'`/`'embeddings'`). Callers handle these differences; the shared code handles everything else.

**Embeddings cost calculation is currently broken and gets fixed by this refactoring.** *(from "Each API surface has two provider-specific concerns")*
The current code passes `api_flavor='chat'` for embeddings (it only checks for the Responses type). `genai_prices` requires `api_flavor='embeddings'` for embedding responses — the `'chat'` flavor fails because it expects `completion_tokens`. The error is silently swallowed by the broad `except Exception: pass`. The refactored code determines the correct `api_flavor` for each response type.

**Everything else about setting usage attributes is the same and belongs in shared code.** *(from "Each API surface has two provider-specific concerns")*
Given the extracted token counts, the usage object, the full response, and the pricing parameters, the shared code: sets `INPUT_TOKENS` and `OUTPUT_TOKENS`, sets `USAGE_RAW` from the usage object via `model_dump(exclude_none=True)`, and computes `operation.cost` from the full response via `genai_prices` (try/except since it's optional).

**Token attributes, raw usage, and cost must fail independently.** *(from "Everything else about setting usage attributes")*
If cost calculation fails, token counts and raw usage must still be set. Cost failures are expected (e.g. unknown model) and should be silently ignored. Other unexpected errors should be surfaced via `handle_internal_errors`.

**`genai_prices` is an optional dependency.** *(from "Token attributes, raw usage, and cost must fail independently")*
It must not be imported at module level. Cost calculation uses it when available; failures are silently caught. Token extraction cannot depend on it.

**Usage attributes are set regardless of semconv version.** *(from "The long-term goal")*
The version system (`SemconvVersion`) controls other attribute formatting. Usage attributes are small values where duplication across versions is intentional.

**Existing `response_data.usage` in version 1 must not be removed.** *(from "Usage attributes are set regardless of semconv version")*
This is existing behavior in OpenAI non-streaming. The new shared code adds attributes alongside `response_data`, not instead of it.
