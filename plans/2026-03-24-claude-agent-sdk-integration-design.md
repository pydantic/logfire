# Claude Agent SDK Integration (Native)

A first-party `logfire.instrument_claude_agent_sdk()` that instruments the Claude Agent SDK with OpenTelemetry spans, with no third-party tracing dependencies.

## Context

The Claude Agent SDK communicates with Claude Code CLI via a subprocess with JSON-RPC over stdin/stdout. It exposes:
- An async message stream (`receive_response()`) yielding `AssistantMessage`, `UserMessage`, `SystemMessage`, `ResultMessage`
- A hook system (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`) for intercepting tool execution

The SDK does not use the `anthropic` package and has no built-in OpenTelemetry support.

## Design decisions

- **Monkey-patching at the class level**: Patch `ClaudeSDKClient.__init__`, `ClaudeSDKClient.query`, and `ClaudeSDKClient.receive_response` directly on the class. This matches the existing logfire pattern (see `instrument_llm_provider`, MCP integration). Hook injection in `__init__` is the critical piece — deviating risks hitting SDK internals that don't support late hook injection.
- **No subagent nesting for v1**: Task tool calls are treated like any other tool. Nested subagent span hierarchies can be added later.
- **No per-instance instrumentation for v1**: Only global instrumentation via class-level patching. Since we monkey-patch at the class level, `query()` and `receive_response()` patches will affect existing instances too (Python method resolution looks at the class). However, `__init__` won't re-run, so existing instances won't have hooks injected — tool call spans won't be created for them. Only instances created after `instrument_claude_agent_sdk()` get full instrumentation.
- **Practical span structure**: We are not targeting full OTel GenAI semantic conventions. The span structure is practical and covers the information that matters for observability.

## Public API

```python
logfire.instrument_claude_agent_sdk()
```

No arguments. Patches `ClaudeSDKClient` globally. Returns an `AbstractContextManager[None]` that reverts the instrumentation when exited (consistent with other logfire integrations like `instrument_anthropic`). The instrumentation is applied immediately — using the context manager is optional.

Method added to `Logfire` class in `main.py`, aliased in `logfire/__init__.py`, with a no-op stub in `logfire-api`.

## File structure

```
logfire/_internal/integrations/claude_agent_sdk.py   # all implementation
```

Single file. No subdirectory, no separate public types module needed.

## Span structure

```
claude.conversation                      # root span, wraps receive_response()
├── claude.assistant.turn                # per AssistantMessage
├── <tool_name>                          # per tool call (via hooks)
├── claude.assistant.turn                # next turn after tool results
├── <tool_name>
└── ...
```

### Root span: `claude.conversation`

Created when `receive_response()` is called. Ended when the stream completes.

Attributes:
- `prompt`: the user's prompt (string)
- `system_prompt`: from options, if present

On completion (from `ResultMessage`):
- `usage.input_tokens`, `usage.output_tokens`, `usage.total_tokens`
- `usage.input_token_details.cache_read`, `usage.input_token_details.cache_creation` (if present)
- `total_cost_usd`
- `num_turns`, `session_id`, `duration_ms`, `is_error`

### Assistant turn span: `claude.assistant.turn`

Created for each `AssistantMessage`. Contains the message content as attributes.

Attributes:
- `content`: flattened content blocks (text, thinking, tool_use as dicts)
- `model`: from `AssistantMessage.model` if present

### Tool spans: `<tool_name>`

Created by `PreToolUse` hook, ended by `PostToolUse` or `PostToolUseFailure` hook.

Attributes on start:
- `tool_input`: the tool's input dict

On completion:
- `tool_response`: the tool's output (string)
- Or `error`: error string on failure

## Implementation details

### Patching mechanism

All three methods (`__init__`, `query`, `receive_response`) are monkey-patched directly on the `ClaudeSDKClient` class using `functools.wraps`. The original methods are saved and called by the patched versions. An `_is_instrumented_by_logfire` guard prevents double-patching.

### Patching `__init__`

The patched `__init__` calls the original, initializes `self._logfire_prompt = None`, then calls `_inject_tracing_hooks(self.options)` to inject three `HookMatcher` entries into `options.hooks`:
- `PreToolUse` -> `pre_tool_use_hook`
- `PostToolUse` -> `post_tool_use_hook`
- `PostToolUseFailure` -> `post_tool_use_failure_hook`

Hooks are inserted at position 0 (before any user-defined hooks). An `_logfire_hooks_injected` flag on the options object prevents duplicate injection.

### Patching `query`

The patched `query` captures the prompt on `self._logfire_prompt` before calling the original. This is needed because `receive_response()` doesn't receive the prompt — `query()` does. For string prompts, stored directly. For non-string, non-AsyncIterable prompts, stringified.

### Patching `receive_response`

The patched `receive_response` wraps the original async generator:

1. Opens root span `claude.conversation` with prompt and system_prompt attributes
2. Sets the parent span and logfire instance in thread-local storage (for hooks)
3. Creates a `_TurnTracker` for managing assistant turn spans
4. Iterates messages from the original generator
5. On `AssistantMessage`: closes the previous turn span if open, opens a new sibling `claude.assistant.turn` span
6. On `ResultMessage`: records usage, cost, and metadata on the root span via `_record_result`
7. Yields each message unchanged
8. In `finally`: closes turn tracker, clears parent span, cleans up orphaned tool spans

### Context propagation

Hooks run in a separate async context where OTel contextvars are empty. The Claude Agent SDK uses anyio internally, and anyio tasks don't propagate contextvars from the parent. We use `threading.local()` to store the current parent span and logfire instance so hooks can create child spans under the correct parent. The parent context is explicitly attached via `trace_api.set_span_in_context` + `context_api.attach` before creating each tool span.

### Utility functions

- `flatten_content_blocks(content)` — converts SDK content block objects (TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock) into serializable dicts. Uses `block.__class__.__name__` for type dispatch (not `type(block).__name__`, because Mock objects override `__class__`).
- `_extract_tool_result_text(content)` — extracts text from tool result content blocks (handles str, list of dicts, list of objects with `.text`)
- `extract_usage_metadata(usage)` — extracts input_tokens, output_tokens, cache tokens from a usage object or dict
- `get_usage_from_result(usage)` — wraps `extract_usage_metadata` and computes totals: input_tokens includes cache tokens, total_tokens = input + output

### Hook callbacks

- `pre_tool_use_hook(input_data, tool_use_id, context)` — creates a child span under the current parent, stores `(span, context_token)` keyed by `tool_use_id`
- `post_tool_use_hook(input_data, tool_use_id, context)` — retrieves the span by `tool_use_id`, sets `tool_response` attribute, ends the span, detaches context
- `post_tool_use_failure_hook(input_data, tool_use_id, context)` — same but sets `error` attribute

All hooks return `{}` (empty dict) to allow execution to proceed normally. All hook logic is wrapped with `handle_internal_errors`.

Active tool spans are tracked in a module-level `_active_tool_spans` dict keyed by `tool_use_id`. Orphaned spans are cleaned up via `_clear_active_tool_spans()` when the conversation ends.

### Uninstrumentation

`instrument_claude_agent_sdk` returns a `contextmanager` that restores the original methods and clears the `_is_instrumented_by_logfire` flag when exited.

## Testing

The Claude Agent SDK communicates via a subprocess (Claude Code CLI), so tests use a custom `MockTransport` that implements the SDK's `Transport` protocol:

- Handles the initialize handshake (control_request/response)
- Yields predefined response messages after the user query
- Dispatches hook callbacks for tool_use blocks via the control protocol (PreToolUse, PostToolUse, PostToolUseFailure)
- Supports marking specific tool_use_ids as failures via `tool_failure_ids`

Tests use the real `ClaudeSDKClient` with the mock transport, exercising the actual monkey-patched methods. An autouse fixture instruments and uninstruments between tests.

**ResourceWarning handling:** The SDK's `Query.close()` doesn't close anyio `MemoryObjectStreams`. They get GC'd during pytest cleanup, triggering `ResourceWarning` via `__del__` → `sys.unraisablehook` → `PytestUnraisableExceptionWarning`. A module-level `pytestmark` suppresses this, and a `_force_gc()` helper in the fixture teardown temporarily replaces `sys.unraisablehook` to suppress ResourceWarning during collection.

## Documentation

`docs/integrations/llms/claude-agent-sdk.md` shows the native integration pattern:

```python
import logfire

logfire.configure()
logfire.instrument_claude_agent_sdk()
```

## Known limitations (v1)

- No per-instance instrumentation — only global
- No subagent/Task tool nesting — subagent calls appear as flat tool spans
- Existing instances get `query`/`receive_response` wrapping (conversation + turn spans) but not hooks (no tool spans), because `__init__` already ran
