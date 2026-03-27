# Merge Consecutive AssistantMessages into a Single Chat Span

**The Claude Agent SDK can split a single model response across multiple `AssistantMessage` objects.** For example, a response with thinking + tool_use arrives as two consecutive messages: one with a `ThinkingBlock`, then another with a `ToolUseBlock`. Both are from the same API call and carry identical usage metadata. This is normal SDK behavior — not an edge case.

**The current implementation creates a separate chat span for each `AssistantMessage`, which loses input context.** *(from "The Claude Agent SDK can split a single model response")*
`_TurnTracker.start_turn()` closes the previous span and opens a new one on every `AssistantMessage`. After the first span consumes `_pending_input` (the user prompt) and resets it to `[]`, the second span finds `_pending_input` empty and records no `gen_ai.input.messages`. This produces a chat span with output (the tool_call) but no input — it's unclear from the span alone what prompted the tool call.

Observed in `test_tool_use_conversation_cassette`:
```
chat (span_id=3): input=[user prompt],      output=[reasoning]    ← OK
chat (span_id=5): input=MISSING,            output=[tool_call]    ← BUG
execute_tool (span_id=7)
chat (span_id=9): input=[tool result],      output=[text]         ← OK
```

**The fix: merge consecutive `AssistantMessage`s into a single chat span by keeping the span open.** *(from "The current implementation creates a separate chat span")*
In `start_turn`, detect whether this is a consecutive message from the same API call: `_pending_input` is empty AND `_current_span` is already open. When true, append the new message's output parts to the existing span's `gen_ai.output.messages` via `set_attribute()` and update usage. When false (first turn, or tool results arrived between turns), close the old span and open a new one as before.

```
AssistantMessage(ThinkingBlock)  → open span, output=[reasoning], input=[user prompt]
AssistantMessage(ToolUseBlock)   → _pending_input empty, span open → merge:
                                   output=[reasoning, tool_call], usage overwritten
  (tool hooks fire, add_tool_result populates _pending_input)
AssistantMessage(TextBlock)      → _pending_input non-empty → close old span, open new one
                                   input=[tool result], output=[text]
```

Result: two chat spans instead of three, each with complete input context and output content matching a single LLM API call.

**Merging uses `set_attribute` to append output parts — no span buffering or delayed creation.** *(from "The fix: merge consecutive AssistantMessages")*
The span is already open and its output_messages attribute was set at creation. On merge, read the existing parts list (tracked on `_TurnTracker` since OTel attributes aren't readable), extend it with the new message's parts, and call `set_attribute(OUTPUT_MESSAGES, ...)` with the combined list. Usage fields are overwritten (not summed) since consecutive messages from the same API call carry identical usage.

**`_TurnTracker` needs to track the current span's output parts for merging.** *(from "Merging uses set_attribute to append output parts")*
Add a `_current_output_parts: list[MessagePart]` field, populated on span creation, extended on merge. This avoids reading back from OTel span attributes (which isn't reliably supported).

**How LangSmith handles this differently (for reference, not to copy).** *(from "The current implementation creates a separate chat span")*
LangSmith creates a new LLM run for every `AssistantMessage` (same as current logfire behavior) but accumulates all messages in a `collected` list. Each LLM run receives the full conversation history as input (prompt + all prior assistant messages + tool results). This means the second run's input includes the original prompt and the first assistant's thinking block. We don't copy this approach because repeating the full history on every span is redundant — merging consecutive messages into one span is cleaner and more accurate (one span = one API call).

**The `post_tool_use_failure_hook` should also feed results into `_pending_input`.** *(from "The fix: merge consecutive AssistantMessages")*
Currently only `post_tool_use_hook` calls `turn_tracker.add_tool_result()`. When a tool fails, `post_tool_use_failure_hook` sets `error.type` on the tool span but doesn't record the error as a tool result for the next turn. This means the next chat span's input messages are incomplete after a tool failure — the model received the error as a `ToolResultBlock`, but the span doesn't show it. The failure hook should call `add_tool_result` with the error text so the next turn's input is complete.

**Updates needed in the main spec.** *(from "The fix: merge consecutive AssistantMessages")*
The main `spec.md` says "One per `AssistantMessage`" for chat spans. This should change to "One per model API call (which may produce multiple `AssistantMessage` objects that are merged)." The hierarchy diagram and the `_TurnTracker` description also need updating to reflect merging.
