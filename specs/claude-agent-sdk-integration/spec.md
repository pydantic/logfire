# Claude Agent SDK Integration

**The Claude Agent SDK gets first-party OpenTelemetry instrumentation via `logfire.instrument_claude_agent_sdk()`.**
Context: The SDK communicates with Claude Code CLI via subprocess/JSON-RPC. It exposes an async message stream (`receive_response()`) yielding typed messages, and a hook system (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`) for intercepting tool execution. It has no built-in OTel support and doesn't use the `anthropic` package.

**Instrumentation is via monkey-patching `ClaudeSDKClient` at the class level.** *(from "The Claude Agent SDK gets first-party OTel instrumentation")*
The SDK has no plugin API. We patch `__init__` (to inject tracing hooks), `query` (to capture the prompt via `self._logfire_prompt`, which `receive_response` reads back — needed because `receive_response` doesn't receive the prompt itself), and `receive_response` (to manage spans around the message stream). This matches the existing logfire pattern (see `instrument_llm_provider`, MCP integration). Hook injection in `__init__` is the critical piece — the SDK doesn't support late hook injection. A separate `_logfire_hooks_injected` flag on each options object prevents duplicate hook injection when multiple instances share the same options. Note: `query()`/`receive_response()` patches affect existing instances (Python MRO), but `__init__` won't re-run, so existing instances won't get hooks and won't produce tool spans.

**All hook and message-processing logic is wrapped in `handle_internal_errors`.** *(from "Instrumentation is via monkey-patching")*
Instrumentation errors must never crash user code. Every hook callback and the `receive_response` message loop use `handle_internal_errors` to swallow and log failures.

**The logfire instance uses `with_settings(custom_scope_suffix='claude_agent_sdk')`.** *(from "Instrumentation is via monkey-patching")*
This scopes spans to the integration, consistent with how other integrations create their logfire instances.

**Calling `instrument_claude_agent_sdk()` twice is a no-op.** *(from "Instrumentation is via monkey-patching")*
An `_is_instrumented_by_logfire` flag on the class guards against double-patching.

**The public API is `logfire.instrument_claude_agent_sdk()` — no arguments.** *(from "Instrumentation is via monkey-patching")*
Since instrumentation is global, there's nothing to configure per-call. Returns `AbstractContextManager[None]` that reverts instrumentation when exited — reverting means restoring the original unpatched methods and resetting the `_is_instrumented_by_logfire` flag (consistent with other logfire integrations). The instrumentation is applied immediately — using the context manager is optional.

**Subagent nesting is out of scope.**
Task tool calls appear as flat tool spans like any other tool. Nested subagent span hierarchies can be added later.

**Spans follow OTel GenAI semantic conventions for names, hierarchy, and attributes.** *(from "The Claude Agent SDK gets first-party OTel instrumentation")*
See [otel-genai-spans.md](otel-genai-spans.md) and [otel-genai-agent-spans.md](otel-genai-agent-spans.md) for the full semconv reference. Use constants from `logfire/_internal/integrations/llm_providers/semconv.py` where they exist; use string literals for semconv attributes not yet defined there (e.g. `gen_ai.tool.name`, `gen_ai.tool.call.id`). Use part dict types (`TextPart`, `ToolCallPart`, `OutputMessage`, etc.) from that module for message content. The hierarchy is `invoke_agent` → `chat` + `execute_tool`:

```
invoke_agent                         # root, wraps receive_response()
├── chat {model}                     # per AssistantMessage
├── execute_tool {tool_name}         # per tool call (via hooks)
├── chat {model}                     # next turn
├── execute_tool {tool_name}
└── ...
```

All spans are siblings under `invoke_agent` — tool spans are children of the root, not of the preceding chat span. This is because hooks run independently and don't know which chat turn they belong to.

**Sensitive message attributes are always recorded (no opt-in gate).** *(from "Spans follow OTel GenAI semantic conventions")*
The semconv marks `gen_ai.input.messages`, `gen_ai.output.messages`, and `gen_ai.system_instructions` as opt-in due to PII concerns. We always record them because Logfire is the user's own observability tool — they're instrumenting their own agent and expect to see the content. This goes against the semconv recommendation "don't record by default" but is the right trade-off here.

**The root span is `invoke_agent`.** *(from "Spans follow OTel GenAI semantic conventions")*
Span name: `invoke_agent`. The SDK doesn't expose an agent name, so the semconv `{gen_ai.agent.name}` suffix is omitted. Attributes set at span creation: `gen_ai.operation.name` = `invoke_agent`, `gen_ai.provider.name` = `anthropic`. On start: `gen_ai.input.messages` (prompt as `InputMessages` with part dicts), `gen_ai.system_instructions` (system prompt as `SystemInstructions` with part dicts). On completion (from `ResultMessage`): `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_creation.input_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.response.model`, `gen_ai.conversation.id` (the SDK's session ID), `operation.cost` (from the SDK's `total_cost_usd` — a logfire convention also used by the anthropic and openai integrations, not part of OTel semconv). Additional non-semconv attributes from the SDK's result metadata: `num_turns`, `duration_ms`. When `is_error` is true in the result, the span's level is set to error via `span.set_level('error')` (a logfire API, not OTel span status).

**Chat spans represent each assistant turn.** *(from "Spans follow OTel GenAI semantic conventions")*
Span name: `chat {model}`. One per `AssistantMessage`. Attributes: `gen_ai.operation.name` = `chat`, `gen_ai.response.model` (from `AssistantMessage.model`), `gen_ai.output.messages` (the assistant's content as `OutputMessages` using `TextPart`, `ToolCallPart`, etc. from semconv).

**Tool spans use `execute_tool` and semconv tool attributes.** *(from "Spans follow OTel GenAI semantic conventions")*
Span name: `execute_tool {tool_name}`. Created by `PreToolUse` hook, ended by `PostToolUse`/`PostToolUseFailure`. Attributes: `gen_ai.operation.name` = `execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.call.id` (the `tool_use_id`), `gen_ai.tool.call.arguments` (tool input), `gen_ai.tool.call.result` (tool output on success), `error.type` (on failure).

**The patched `receive_response` drives span lifecycle by inspecting messages from the stream.** *(from "Instrumentation is via monkey-patching", "Spans follow OTel GenAI semantic conventions")*
It wraps the original async generator: opens an `invoke_agent` root span for the entire iteration, then inspects each yielded message. On `AssistantMessage`: closes the previous chat span (if any) and opens a new `chat {model}` sibling. On `ResultMessage`: records usage/cost on the root span and sets error level if `is_error` is true. Each message is yielded through unchanged. If `query` was not called before `receive_response`, the prompt attribute is simply omitted.

**Hooks run in isolated async contexts, so context propagation uses `threading.local()`.** *(from "Instrumentation is via monkey-patching")*
The SDK uses anyio internally, and anyio tasks don't propagate contextvars from the parent. We store the current parent span and logfire instance in `threading.local()` so hooks can create child spans under the correct parent, attaching context explicitly via `trace_api.set_span_in_context` + `context_api.attach`. This relies on all async tasks running on the same thread — if the SDK ever used threaded execution, this approach would need revisiting.

**Active tool spans are tracked by `tool_use_id` to correlate pre/post hooks.** *(from "Tool spans use `execute_tool`", "Hooks run in isolated async contexts")*
`PreToolUse` creates and stores `(span, context_token)`. `PostToolUse`/`PostToolUseFailure` retrieves, sets attributes, ends the span, detaches context. Orphaned spans are cleaned up when the conversation ends.

**Tests use a `MockTransport` implementing the SDK's `Transport` protocol.** *(from "Instrumentation is via monkey-patching")*
Context: The SDK communicates via subprocess, so real calls can't be used in tests. The mock handles the initialize handshake, yields predefined messages, and dispatches hook callbacks for tool_use blocks. Tests exercise the real `ClaudeSDKClient` with actual monkey-patched methods. Note: the SDK's `Query.close()` doesn't close anyio `MemoryObjectStreams`, causing ResourceWarning during GC — tests suppress this via `pytestmark` and a `_force_gc()` teardown helper.
