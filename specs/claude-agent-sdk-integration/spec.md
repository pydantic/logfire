# Claude Agent SDK Integration

**The Claude Agent SDK gets first-party OpenTelemetry instrumentation via `logfire.instrument_claude_agent_sdk()`.**

**The Claude Agent SDK communicates with Claude Code CLI via a subprocess with JSON-RPC over stdin/stdout.** *(from "The Claude Agent SDK gets first-party OpenTelemetry instrumentation")*
It exposes an async message stream (`receive_response()`) yielding `AssistantMessage`, `UserMessage`, `SystemMessage`, `ResultMessage`, and a hook system (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`) for intercepting tool execution. The SDK does not use the `anthropic` package and has no built-in OpenTelemetry support.

**Instrumentation is global, via monkey-patching at the class level.** *(from "The Claude Agent SDK gets first-party OpenTelemetry instrumentation")*
Patch `ClaudeSDKClient.__init__`, `ClaudeSDKClient.query`, and `ClaudeSDKClient.receive_response` directly on the class. This matches the existing logfire pattern (see `instrument_llm_provider`, MCP integration). Hook injection in `__init__` is the critical piece — deviating risks hitting SDK internals that don't support late hook injection.

**No per-instance instrumentation for v1.** *(from "Instrumentation is global, via monkey-patching at the class level")*
Since we monkey-patch at the class level, `query()` and `receive_response()` patches affect existing instances too (Python method resolution looks at the class). However, `__init__` won't re-run, so existing instances won't have hooks injected — tool call spans won't be created for them. Only instances created after `instrument_claude_agent_sdk()` get full instrumentation.

**No subagent nesting for v1.** *(from "The Claude Agent SDK gets first-party OpenTelemetry instrumentation")*
Task tool calls are treated like any other tool. Nested subagent span hierarchies can be added later.

**We are not targeting full OTel GenAI semantic conventions.** *(from "The Claude Agent SDK gets first-party OpenTelemetry instrumentation")*
The span structure is practical and covers the information that matters for observability.

**The public API is a single no-argument call.** *(from "Instrumentation is global, via monkey-patching at the class level")*

```python
logfire.instrument_claude_agent_sdk()
```

Returns an `AbstractContextManager[None]` that reverts the instrumentation when exited (consistent with other logfire integrations like `instrument_anthropic`). The instrumentation is applied immediately — using the context manager is optional. Method added to `Logfire` class in `main.py`, aliased in `logfire/__init__.py`, with a no-op stub in `logfire-api`.

**All implementation lives in a single file: `logfire/_internal/integrations/claude_agent_sdk.py`.** *(from "The public API is a single no-argument call")*
No subdirectory, no separate public types module needed.

**Span structure is a flat tree under a conversation root.** *(from "We are not targeting full OTel GenAI semantic conventions", "No subagent nesting for v1")*

```
claude.conversation                      # root span, wraps receive_response()
├── claude.assistant.turn                # per AssistantMessage
├── <tool_name>                          # per tool call (via hooks)
├── claude.assistant.turn                # next turn after tool results
├── <tool_name>
└── ...
```

**The root span `claude.conversation` wraps `receive_response()`.** *(from "Span structure is a flat tree under a conversation root")*
Created when `receive_response()` is called, ended when the stream completes. Attributes on start: `prompt` (the user's prompt string), `system_prompt` (from options, if present). On completion (from `ResultMessage`): `usage.input_tokens`, `usage.output_tokens`, `usage.total_tokens`, `usage.input_token_details.cache_read`, `usage.input_token_details.cache_creation` (if present), `total_cost_usd`, `num_turns`, `session_id`, `duration_ms`, `is_error`.

**Assistant turn spans `claude.assistant.turn` are created for each `AssistantMessage`.** *(from "Span structure is a flat tree under a conversation root")*
Attributes: `content` (flattened content blocks — text, thinking, tool_use as dicts), `model` (from `AssistantMessage.model` if present).

**Tool spans are named after the tool and managed by hooks.** *(from "Span structure is a flat tree under a conversation root")*
Created by `PreToolUse` hook, ended by `PostToolUse` or `PostToolUseFailure` hook. On start: `tool_input` (the tool's input dict). On completion: `tool_response` (the tool's output string), or `error` (error string on failure).

**All three methods are monkey-patched using `functools.wraps` with a double-patch guard.** *(from "Instrumentation is global, via monkey-patching at the class level")*
The original methods are saved and called by the patched versions. An `_is_instrumented_by_logfire` guard on the class prevents double-patching.

**The patched `__init__` injects tracing hooks into client options.** *(from "All three methods are monkey-patched using `functools.wraps`", "Tool spans are named after the tool and managed by hooks")*
Calls the original, initializes `self._logfire_prompt = None`, then calls `_inject_tracing_hooks(self.options)` to inject three `HookMatcher` entries at position 0 (before user-defined hooks): `PreToolUse` -> `pre_tool_use_hook`, `PostToolUse` -> `post_tool_use_hook`, `PostToolUseFailure` -> `post_tool_use_failure_hook`. An `_logfire_hooks_injected` flag on the options object prevents duplicate injection.

**The patched `query` captures the prompt for later use by `receive_response`.** *(from "All three methods are monkey-patched using `functools.wraps`", "The root span `claude.conversation` wraps `receive_response()`")*
Stores the prompt on `self._logfire_prompt` before calling the original. This is needed because `receive_response()` doesn't receive the prompt — `query()` does. For string prompts, stored directly. For non-string, non-AsyncIterable prompts, stringified.

**The patched `receive_response` wraps the original async generator to manage all spans.** *(from "All three methods are monkey-patched using `functools.wraps`", "Span structure is a flat tree under a conversation root")*

1. Opens root span `claude.conversation` with prompt and system_prompt attributes
2. Sets the parent span and logfire instance in thread-local storage (for hooks)
3. Creates a `_TurnTracker` for managing assistant turn spans
4. Iterates messages from the original generator
5. On `AssistantMessage`: closes the previous turn span if open, opens a new sibling `claude.assistant.turn` span
6. On `ResultMessage`: records usage, cost, and metadata on the root span via `_record_result`
7. Yields each message unchanged
8. In `finally`: closes turn tracker, clears parent span, cleans up orphaned tool spans

**Hooks run in a separate async context where OTel contextvars are empty, so we use `threading.local()` for context propagation.** *(from "The patched `__init__` injects tracing hooks into client options", "The patched `receive_response` wraps the original async generator")*
The Claude Agent SDK uses anyio internally, and anyio tasks don't propagate contextvars from the parent. We store the current parent span and logfire instance in `threading.local()` so hooks can create child spans under the correct parent. The parent context is explicitly attached via `trace_api.set_span_in_context` + `context_api.attach` before creating each tool span.

**Active tool spans are tracked in a module-level dict keyed by `tool_use_id`.** *(from "Tool spans are named after the tool and managed by hooks")*
`pre_tool_use_hook` creates a child span and stores `(span, context_token)`. `post_tool_use_hook` retrieves it, sets `tool_response`, ends the span, detaches context. `post_tool_use_failure_hook` does the same but sets `error`. All hooks return `{}` (empty dict) to allow normal execution. All hook logic is wrapped with `handle_internal_errors`. Orphaned spans are cleaned up via `_clear_active_tool_spans()` when the conversation ends.

**Utility functions handle content serialization and usage extraction.** *(from "The patched `receive_response` wraps the original async generator")*

- `flatten_content_blocks(content)` — converts SDK content block objects into serializable dicts. Uses `block.__class__.__name__` for type dispatch (not `type(block).__name__`, because Mock objects override `__class__`).
- `_extract_tool_result_text(content)` — extracts text from tool result content blocks (handles str, list of dicts, list of objects with `.text`)
- `extract_usage_metadata(usage)` — extracts input_tokens, output_tokens, cache tokens from a usage object or dict
- `get_usage_from_result(usage)` — wraps `extract_usage_metadata` and computes totals: input_tokens includes cache tokens, total_tokens = input + output

**Uninstrumentation restores original methods.** *(from "The public API is a single no-argument call", "All three methods are monkey-patched using `functools.wraps`")*
The context manager returned by `instrument_claude_agent_sdk` restores the original methods and clears the `_is_instrumented_by_logfire` flag when exited.

**Tests use a custom `MockTransport` that implements the SDK's `Transport` protocol.** *(from "The Claude Agent SDK communicates with Claude Code CLI via a subprocess")*
The Claude Agent SDK communicates via a subprocess (Claude Code CLI), so real SDK calls can't be used in tests. The mock handles the initialize handshake, yields predefined response messages after the user query, and dispatches hook callbacks for tool_use blocks via the control protocol. Supports marking specific `tool_use_id`s as failures via `tool_failure_ids`. Tests use the real `ClaudeSDKClient` with the mock transport, exercising the actual monkey-patched methods. An autouse fixture instruments and uninstruments between tests.

**ResourceWarning from SDK internals is suppressed in tests.** *(from "Tests use a custom `MockTransport`")*
The SDK's `Query.close()` doesn't close anyio `MemoryObjectStreams`. They get GC'd during pytest cleanup, triggering `ResourceWarning` via `__del__` -> `sys.unraisablehook` -> `PytestUnraisableExceptionWarning`. A module-level `pytestmark` suppresses this, and a `_force_gc()` helper in the fixture teardown temporarily replaces `sys.unraisablehook` to suppress ResourceWarning during collection.

**Documentation shows the minimal integration pattern.** *(from "The public API is a single no-argument call")*
`docs/integrations/llms/claude-agent-sdk.md` shows:

```python
import logfire

logfire.configure()
logfire.instrument_claude_agent_sdk()
```
