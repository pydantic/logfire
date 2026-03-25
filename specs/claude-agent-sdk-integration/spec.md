# Claude Agent SDK Integration

**The Claude Agent SDK gets first-party OpenTelemetry instrumentation via `logfire.instrument_claude_agent_sdk()`.**
Context: The SDK communicates with Claude Code CLI via subprocess/JSON-RPC. It exposes an async message stream (`receive_response()`) yielding typed messages, and a hook system (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`) for intercepting tool execution. It has no built-in OTel support and doesn't use the `anthropic` package.

**Instrumentation is via monkey-patching `ClaudeSDKClient` at the class level.** *(from "The Claude Agent SDK gets first-party OTel instrumentation")*
The SDK has no plugin API. We patch `__init__` (to inject tracing hooks), `query` (to capture the prompt via `self._logfire_prompt`, which `receive_response` reads back — needed because `receive_response` doesn't receive the prompt itself), and `receive_response` (to manage spans around the message stream). This matches the existing logfire pattern (see `instrument_llm_provider`, MCP integration). Hook injection in `__init__` is the critical piece — the SDK doesn't support late hook injection.

**Calling `instrument_claude_agent_sdk()` twice is a no-op.** *(from "Instrumentation is via monkey-patching")*
An `_is_instrumented_by_logfire` flag on the class guards against double-patching.

**The public API is `logfire.instrument_claude_agent_sdk()` — no arguments.** *(from "Instrumentation is via monkey-patching")*
Since instrumentation is global, there's nothing to configure per-call. Returns `AbstractContextManager[None]` that reverts instrumentation when exited — reverting means restoring the original unpatched methods and resetting the `_is_instrumented_by_logfire` flag (consistent with other logfire integrations). The instrumentation is applied immediately — using the context manager is optional.

**Per-instance instrumentation is out of scope.** *(from "Instrumentation is via monkey-patching")*
Consequence of class-level patching: `query()`/`receive_response()` patches affect existing instances (Python MRO), but `__init__` won't re-run, so existing instances won't get hooks and won't produce tool spans.

**Subagent nesting is out of scope.** *(from "The Claude Agent SDK gets first-party OTel instrumentation")*
Task tool calls appear as flat tool spans like any other tool. Nested subagent span hierarchies can be added later.

**Span structure is a practical flat tree, not full OTel GenAI semantic conventions.** *(from "The Claude Agent SDK gets first-party OTel instrumentation", "Subagent nesting is out of scope")*

```
claude.conversation                      # root, wraps receive_response()
├── claude.assistant.turn                # per AssistantMessage
├── <tool_name>                          # per tool call (via hooks)
├── claude.assistant.turn
└── ...
```

**Span attributes are bare keys, not namespaced.** *(from "Span structure is a practical flat tree")*
Attribute names like `prompt`, `tool_input`, `usage.input_tokens` are the literal OTel attribute keys — no `logfire.claude.*` or GenAI semantic convention prefix.

**The patched `receive_response` drives span lifecycle by inspecting messages from the stream.** *(from "Instrumentation is via monkey-patching", "Span structure is a practical flat tree")*
It wraps the original async generator: opens a `claude.conversation` root span for the entire iteration, then inspects each yielded message. On `AssistantMessage`: closes the previous turn span (if any) and opens a new `claude.assistant.turn` sibling. On `ResultMessage`: records usage/cost on the root span. Each message is yielded through unchanged. If `query` was not called before `receive_response`, the prompt attribute is simply omitted.

**The root span `claude.conversation` captures prompt, usage, and cost.** *(from "The patched `receive_response` drives span lifecycle")*
On start: `prompt`, `system_prompt`. On completion (from `ResultMessage`): `usage.input_tokens`, `usage.output_tokens`, `usage.total_tokens`, cache token details, `total_cost_usd`, `num_turns`, `session_id`, `duration_ms`, `is_error`. If the stream raises an exception, the root span records it via OTel's standard span exception/status mechanism (the `LogfireSpan` context manager handles this).

**Turn spans capture the assistant's message content and model.** *(from "Span structure is a practical flat tree")*
`content` (flattened content blocks as dicts), `model` (from `AssistantMessage.model`).

**Tool spans use the tool name as span name and capture input/output.** *(from "Span structure is a practical flat tree")*
On start: `tool_input`. On success: `tool_response`. On failure: `error`.

**Hooks run in isolated async contexts, so context propagation uses `threading.local()`.** *(from "Instrumentation is via monkey-patching")*
The SDK uses anyio internally, and anyio tasks don't propagate contextvars from the parent. We store the current parent span and logfire instance in `threading.local()` so hooks can create child spans under the correct parent, attaching context explicitly via `trace_api.set_span_in_context` + `context_api.attach`. This relies on all async tasks running on the same thread — if the SDK ever used threaded execution, this approach would need revisiting.

**Active tool spans are tracked by `tool_use_id` to correlate pre/post hooks.** *(from "Tool spans use the tool name as span name", "Hooks run in isolated async contexts")*
`PreToolUse` creates and stores `(span, context_token)`. `PostToolUse`/`PostToolUseFailure` retrieves, sets attributes, ends the span, detaches context. Orphaned spans are cleaned up when the conversation ends.

**Tests use a `MockTransport` implementing the SDK's `Transport` protocol.** *(from "The Claude Agent SDK gets first-party OTel instrumentation")*
Context: The SDK communicates via subprocess, so real calls can't be used in tests. The mock handles the initialize handshake, yields predefined messages, and dispatches hook callbacks for tool_use blocks. Tests exercise the real `ClaudeSDKClient` with actual monkey-patched methods. Note: the SDK's `Query.close()` doesn't close anyio `MemoryObjectStreams`, causing ResourceWarning during GC — tests suppress this via `pytestmark` and a `_force_gc()` teardown helper.
