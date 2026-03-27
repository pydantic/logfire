# Chat Span Input/Output Completeness

**Each chat span should be independently readable — it should contain the full set of input and output messages for that LLM call.** A user looking at a single chat span in the Logfire UI should see the complete conversation context the model received and the complete response it produced, without needing to correlate across sibling spans. This is the fundamental requirement that drives the other changes in this spec.

**Input messages should include the full accumulated conversation history, not just incremental changes.** *(from "Each chat span should be independently readable")*
The `_TurnTracker` should maintain a running `_history` list. After each turn's span is opened, append the current turn's output (as an assistant `ChatMessage`) to `_history`. When tool results arrive via `add_tool_result`, append those too. The next turn's `INPUT_MESSAGES` is then the full `_history`. The first turn gets the user prompt. Subsequent turns include the user prompt, all prior assistant outputs, and all tool results.

```
chat 1: input=[user prompt],
        output=[reasoning, tool_call]
  → append to history: assistant(reasoning, tool_call)
  → tool result arrives → append to history: tool(result)
chat 2: input=[user prompt, assistant(reasoning, tool_call), tool result],
        output=[text]
```

The trade-off is redundant data across spans (each repeats the full history), but this is what makes each span self-contained — essential for debugging and for the Logfire UI where users click into individual spans.

**Consecutive `AssistantMessage`s from the same API call should be merged into a single chat span.** *(from "Each chat span should be independently readable")*
The Claude Agent SDK can split a single model response across multiple `AssistantMessage` objects. For example, a response with thinking + tool_use arrives as two consecutive messages: one with a `ThinkingBlock`, then another with a `ToolUseBlock`. Both are from the same API call and carry identical usage metadata. This is normal SDK behavior — not an edge case.

In `start_turn`, detect whether this is a consecutive message from the same API call: no tool results arrived between messages (`_pending_input` unchanged) AND a span is already open. When true, append the new message's output parts to the existing span's `gen_ai.output.messages` via `set_attribute()` and update usage. When false (first turn, or tool results arrived between turns), close the old span and open a new one.

```
AssistantMessage(ThinkingBlock)  → open span, output=[reasoning], input=[user prompt]
AssistantMessage(ToolUseBlock)   → no new input, span open → merge:
                                   output=[reasoning, tool_call], usage overwritten
  (tool hooks fire, add_tool_result populates history)
AssistantMessage(TextBlock)      → history has new tool results → close old span, open new one
                                   input=[user prompt, assistant(reasoning, tool_call), tool result],
                                   output=[text]
```

**Merging uses `set_attribute` to append output parts — no span buffering or delayed creation.** *(from "Consecutive AssistantMessages should be merged")*
The span is already open and its output_messages attribute was set at creation. On merge, read the existing parts list (tracked on `_TurnTracker` via `_current_output_parts` since OTel attributes aren't readable), extend it with the new message's parts, and call `set_attribute(OUTPUT_MESSAGES, ...)` with the combined list. Usage fields are overwritten (not summed) since consecutive messages from the same API call carry identical usage.

**The `post_tool_use_failure_hook` should also feed results into the history.** *(from "Input messages should include the full accumulated conversation history")*
Currently only `post_tool_use_hook` calls `turn_tracker.add_tool_result()`. When a tool fails, `post_tool_use_failure_hook` sets `error.type` on the tool span but doesn't record the error as a tool result for the next turn. This means the next chat span's input messages are incomplete after a tool failure — the model received the error as a `ToolResultBlock`, but the span doesn't show it. The failure hook should call `add_tool_result` with the error text so the next turn's input is complete.

**Per-message `output_tokens` from the SDK is unreliable.** *(from "Each chat span should be independently readable")*
The SDK reports `output_tokens: 0` on intermediate `AssistantMessage`s (e.g. thinking blocks, tool_use blocks) because these are streamed chunks with `stop_reason: null`. The accurate total output token count is only available on the `ResultMessage`, which goes on the root `invoke_agent` span. Per-turn chat spans will show misleading output_tokens values — this is a limitation of the SDK's per-message usage reporting, not a bug in our instrumentation.

**Updates needed in the main spec.** *(from "Consecutive AssistantMessages should be merged")*
The main `spec.md` says "One per `AssistantMessage`" for chat spans. This should change to "One per model API call (which may produce multiple `AssistantMessage` objects that are merged)." The hierarchy diagram and the `_TurnTracker` description also need updating to reflect merging. The `gen_ai.input.messages` description should reflect full history accumulation.
