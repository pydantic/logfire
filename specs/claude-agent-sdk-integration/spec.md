# Claude Agent SDK Integration

**The Claude Agent SDK gets first-party OpenTelemetry instrumentation via `logfire.instrument_claude_agent_sdk()`.**
Context: The SDK communicates with Claude Code CLI via subprocess/JSON-RPC. It exposes an async message stream (`receive_response()`) yielding typed messages, and a hook system (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`) for intercepting tool execution. It has no built-in OTel support and doesn't use the `anthropic` package.

**Instrumentation is via monkey-patching `ClaudeSDKClient` at the class level.** *(from "The Claude Agent SDK gets first-party OTel instrumentation")*
The SDK has no plugin API. We patch `__init__` (to inject tracing hooks), `query` (to capture the prompt via `self._logfire_prompt`, which `receive_response` reads back — needed because `receive_response` doesn't receive the prompt itself), and `receive_response` (to manage spans around the message stream). This matches the existing logfire pattern (see `instrument_llm_provider`, MCP integration). Hook injection in `__init__` is the critical piece — the SDK doesn't support late hook injection. Note: `query()`/`receive_response()` patches affect existing instances (Python MRO), but `__init__` won't re-run, so existing instances won't get hooks and won't produce tool spans.

**All hook and message-processing logic is wrapped in `handle_internal_errors`.** *(from "Instrumentation is via monkey-patching")*
Instrumentation errors must never crash user code. Every hook callback and the `receive_response` message loop use `handle_internal_errors` to swallow and log failures.

**The logfire instance uses `with_settings(custom_scope_suffix='claude_agent_sdk')`.** *(from "Instrumentation is via monkey-patching")*
This scopes spans to the integration, consistent with how other integrations create their logfire instances.

**Calling `instrument_claude_agent_sdk()` twice is a no-op.** *(from "Instrumentation is via monkey-patching")*
An `_is_instrumented_by_logfire` flag on the class guards against double-patching.

**The public API is `logfire.instrument_claude_agent_sdk()` — no arguments.** *(from "Instrumentation is via monkey-patching")*
Since instrumentation is global, there's nothing to configure per-call. Returns `AbstractContextManager[None]` that reverts instrumentation when exited — reverting means restoring the original unpatched methods and resetting the `_is_instrumented_by_logfire` flag (consistent with other logfire integrations). The instrumentation is applied immediately — using the context manager is optional.

**Spans follow OTel GenAI semantic conventions for names, hierarchy, and attributes.** *(from "The Claude Agent SDK gets first-party OTel instrumentation")*
See [otel-genai-spans.md](otel-genai-spans.md) and [otel-genai-agent-spans.md](otel-genai-agent-spans.md) for the full semconv reference. All semconv attribute names are defined as constants in `logfire/_internal/integrations/llm_providers/semconv.py`: `SYSTEM`, `PROVIDER_NAME`, `OPERATION_NAME`, `RESPONSE_MODEL`, `INPUT_TOKENS`, `OUTPUT_TOKENS`, `CACHE_READ_INPUT_TOKENS`, `CACHE_CREATION_INPUT_TOKENS`, `INPUT_MESSAGES`, `OUTPUT_MESSAGES`, `SYSTEM_INSTRUCTIONS`, `CONVERSATION_ID`, `TOOL_NAME`, `TOOL_CALL_ID`, `TOOL_CALL_ARGUMENTS`, `TOOL_CALL_RESULT`, `ERROR_TYPE`. Part dict types (`TextPart`, `ToolCallPart`, `ReasoningPart`, `OutputMessage`, etc.) are also from that module. Logfire-specific conventions like `operation.cost` remain as string literals. The hierarchy is `invoke_agent` → `chat` + `execute_tool`:

```
invoke_agent                         # root, wraps receive_response()
├── chat {model}                     # per LLM API call (may merge multiple AssistantMessages)
├── execute_tool {tool_name}         # per tool call (via hooks)
├── chat {model}                     # next turn
├── execute_tool {tool_name}
└── ...
```

All spans are siblings under `invoke_agent` — tool spans are children of the root, not of the preceding chat span. This is because hooks run independently and don't know which chat turn they belong to.

**Subagent nesting is out of scope.** *(from "Spans follow OTel GenAI semantic conventions")*
Task tool calls appear as flat tool spans like any other tool. Nested subagent span hierarchies can be added later.

**Sensitive message attributes are always recorded (no opt-in gate).** *(from "Spans follow OTel GenAI semantic conventions")*
The semconv marks `gen_ai.input.messages`, `gen_ai.output.messages`, and `gen_ai.system_instructions` as opt-in due to PII concerns. We always record them because Logfire is the user's own observability tool — they're instrumenting their own agent and expect to see the content. This goes against the semconv recommendation "don't record by default" but is the right trade-off here.

**The root span is `invoke_agent`.** *(from "Spans follow OTel GenAI semantic conventions")*
Span name: `invoke_agent`. The SDK doesn't expose an agent name, so the semconv `{gen_ai.agent.name}` suffix is omitted. Attributes set at span creation: `gen_ai.operation.name` = `invoke_agent`, `gen_ai.system` = `anthropic`, `gen_ai.provider.name` = `anthropic`. On start: `gen_ai.input.messages` (prompt as `InputMessages` with part dicts), `gen_ai.system_instructions` (system prompt as `SystemInstructions` with part dicts). On completion (from `ResultMessage`): `gen_ai.usage.input_tokens` (total: `input_tokens + cache_read + cache_creation`), `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_creation.input_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.response.model`, `gen_ai.conversation.id` (the SDK's session ID), `operation.cost` (from the SDK's `total_cost_usd` — a logfire convention also used by the anthropic and openai integrations, not part of OTel semconv). Additional non-semconv attributes from the SDK's result metadata: `num_turns`, `duration_ms`. When `is_error` is true in the result, the span's level is set to error via `span.set_level('error')` (a logfire API, not OTel span status).

**Chat spans represent each LLM API call — these are the most important spans.** *(from "Spans follow OTel GenAI semantic conventions")*
Span name: `chat {model}`. One per LLM API call, which may produce multiple `AssistantMessage` objects that are merged into a single span. Chat spans should follow the OTel GenAI semconv for the `chat` operation as closely as possible. The SDK's `AssistantMessage` provides: `content` (response blocks), `model` (string), `usage` (per-turn token usage dict with `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`), and `error` (optional error type string).

Attributes:
- `gen_ai.operation.name` = `chat`
- `gen_ai.system` = `anthropic`
- `gen_ai.provider.name` = `anthropic`
- `gen_ai.response.model` (from `AssistantMessage.model`)
- `gen_ai.output.messages` (the assistant's content as `OutputMessages` using `TextPart`, `ToolCallPart`, etc. from semconv)
- `gen_ai.input.messages` — the full accumulated conversation history up to this turn. Each chat span should be independently readable: a user looking at a single span should see the complete set of messages the model received. The first turn has the user prompt. Subsequent turns include the user prompt, all prior assistant outputs (as assistant `ChatMessage`s), and all tool results. The `_TurnTracker` maintains a running `_history` list: after each turn, the current output is appended as an assistant message; tool results from hooks are appended as they arrive. The next turn's `INPUT_MESSAGES` is this full history. This means later spans repeat earlier content, but it makes each span self-contained for debugging.
- `gen_ai.usage.input_tokens` — the **total** number of input tokens for this turn, computed as `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` from `AssistantMessage.usage`. The OTel GenAI semconv defines this as the total input token count; the Anthropic API's `input_tokens` field only counts uncached tokens, so we must sum all three to get the actual total.
- `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_creation.input_tokens` (from `AssistantMessage.usage`, when present — these are Anthropic-specific breakdowns, not part of OTel semconv)
- `gen_ai.usage.output_tokens` is **not set** on chat spans. The SDK reports `output_tokens: 0` on intermediate `AssistantMessage`s (streamed chunks with `stop_reason: null`). The accurate total is only available on the `ResultMessage` and goes on the root `invoke_agent` span.
- `error.type` (when `AssistantMessage.error` is set — e.g. `'rate_limit'`, `'server_error'`)

**Tool spans use `execute_tool` and semconv tool attributes.** *(from "Spans follow OTel GenAI semantic conventions")*
Span name: `execute_tool {tool_name}`. Created by `PreToolUse` hook, ended by `PostToolUse`/`PostToolUseFailure`. Attributes: `gen_ai.operation.name` = `execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.call.id` (the `tool_use_id`), `gen_ai.tool.call.arguments` (tool input), `gen_ai.tool.call.result` (tool output on success), `error.type` (on failure). Both `PostToolUse` and `PostToolUseFailure` hooks feed results into the conversation history via `turn_tracker.add_tool_result()` so the next chat span's input messages are complete — including after tool failures.

**Chat span timing approximates the LLM API call duration.** *(from "Chat spans represent each LLM API call")*
Chat spans are opened when the LLM call starts and closed before tool execution begins, so their duration covers the model's thinking time only — not tool execution or the next turn's processing. The `_TurnTracker.open_chat_span()` method opens a span with input messages; `handle_assistant_message()` later populates it with output, model, and usage. For the first turn, `open_chat_span()` is called immediately after creating the tracker (the LLM starts processing at query time). For subsequent turns, it's called when a `UserMessage` arrives (tool results sent back to the model, next LLM call starts). Spans are closed by `close_chat_span()`, called from the `PreToolUse` hook (before tool execution starts), from `open_chat_span()` (before opening the next turn's span), or from `close()` (at conversation end). Because chat spans may be closed from hooks running in different async contexts, they use `_start()` / `_end()` instead of `__enter__()` / `__exit__()` — avoiding the OTel context stack entirely.

**Consecutive `AssistantMessage`s from the same API call are merged into a single chat span.** *(from "Chat span timing approximates the LLM API call duration")*
The SDK can split a single model response across multiple `AssistantMessage` objects (e.g. ThinkingBlock then ToolUseBlock). Since the span is already open when `handle_assistant_message` is called, it simply extends the output parts and overwrites usage (consecutive messages carry identical usage). No separate merge detection is needed — the span was opened at the right time, and each `AssistantMessage` adds to it.

**The patched `receive_response` drives span lifecycle by inspecting messages from the stream.** *(from "Instrumentation is via monkey-patching", "Spans follow OTel GenAI semantic conventions")*
It wraps the original async generator: opens an `invoke_agent` root span for the entire iteration, then inspects each yielded message. On `AssistantMessage`: populates the current chat span with output and usage via `handle_assistant_message`. On `UserMessage`: closes the current chat span and opens a new one via `handle_user_message` (which calls `open_chat_span`). On `ResultMessage`: records usage/cost on the root span and sets error level if `is_error` is true. Each message is yielded through unchanged. If `query` was not called before `receive_response`, the prompt attribute is simply omitted.

**Hooks run in isolated async contexts, so context propagation uses `threading.local()`.** *(from "Instrumentation is via monkey-patching")*
The SDK uses anyio internally, and anyio tasks don't propagate contextvars from the parent. We store the current parent span and logfire instance in `threading.local()` so hooks can create child spans under the correct parent, attaching context explicitly via `trace_api.set_span_in_context` + `context_api.attach`. This relies on all async tasks running on the same thread — if the SDK ever used threaded execution, this approach would need revisiting.

**Active tool spans are tracked by `tool_use_id` to correlate pre/post hooks.** *(from "Tool spans use `execute_tool`", "Hooks run in isolated async contexts")*
`PreToolUse` creates and stores `(span, context_token)`. `PostToolUse`/`PostToolUseFailure` retrieves, sets attributes, ends the span, detaches context. Orphaned spans are cleaned up when the conversation ends.

**Integration tests use cassette-based record/replay through the real `SubprocessCLITransport`.** *(from "Instrumentation is via monkey-patching")*
The SDK communicates via subprocess, so real calls can't be used in CI. Instead of mocking the transport layer, we replace the subprocess itself: `ClaudeAgentOptions.cli_path` points to `fake_claude.py`, a Python script that replays recorded I/O. This means the real transport's pipe handling, JSON parsing, and process lifecycle all execute during tests.

**`fake_claude.py` acts as both recorder and replayer.** *(from "Integration tests use cassette-based record/replay")*
Controlled by environment variables (`CASSETTE_MODE`, `CASSETTE_PATH`, `REAL_CLAUDE_PATH`):

- **Record mode** (`--record-claude-cassettes` pytest flag): Spawns the real `claude` CLI as a child, proxies stdin/stdout, and tees every message to a cassette file. ID fields are normalized during recording so cassettes are deterministic.
- **Replay mode** (default): Reads the cassette file, replays stdout messages, and consumes stdin at the correct points to maintain protocol timing. Also handles the `-v` version check that `SubprocessCLITransport` runs before the main conversation.

**Cassette files are JSON with ordered message entries.** *(from "fake_claude.py acts as both recorder and replayer")*
Format: `{"metadata": {...}, "messages": [{"direction": "send"|"recv", "message": <JSON>}, ...]}`. Stored in `tests/otel_integrations/cassettes/test_claude_agent_sdk/`. Each cassette is recorded from a real Claude session and committed to the repo. CI always runs in replay mode.

**Only real cassettes are allowed — no hand-crafted or synthetic fixtures.** *(from "Cassette files are JSON with ordered message entries")*
All cassette files must be producible via `--record-claude-cassettes`. Defensive code paths that handle rare server-side conditions (e.g. `AssistantMessage.error`, `ResultMessage.is_error=True`, missing usage) use `# pragma: no cover` or `# pragma: no branch` instead of fabricated test data.

**Unit tests for pure helper functions use Mock objects, not cassettes.** *(from "Integration tests use cassette-based record/replay")*
Tests for `_content_blocks_to_output_messages`, `_extract_usage`, hook functions, and hook injection are standalone unit tests with no dependency on the SDK transport.

**Test teardown closes streams the SDK neglects.** *(from "Integration tests use cassette-based record/replay")*
The SDK's `Query.close()` doesn't close its internal `MemoryObjectSendStream` / `MemoryObjectReceiveStream`, and `SubprocessCLITransport.close()` doesn't close stdout. Tests explicitly close these before `client.disconnect()` via `_close_sdk_streams()` to prevent `ResourceWarning` on GC — no warning suppression or forced GC needed.
