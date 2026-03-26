# Eliminate Synthetic Cassettes

**Synthetic cassettes are not maintainable.**
Hand-crafted JSON cassettes derived from real recordings break silently when the SDK or CLI protocol changes. Re-recording the base cassettes is easy (`--record-cassettes`), but the synthetic variants must be manually re-derived each time — a process that's error-prone and doesn't scale.

**The mock transport is also not the answer.** *(from "Synthetic cassettes are not maintainable")*
The previous `MockTransport` (removed in PR #1808) was ~1000 lines of convoluted logic reimplementing SDK protocol behavior. The fix for bad test infrastructure is not different bad test infrastructure.

**Real cassettes recorded from real sessions are the only integration test fixtures.** *(from "Synthetic cassettes are not maintainable", "The mock transport is also not the answer")*
All cassette files must be recordable via `--record-cassettes`. If a cassette can't be produced by a real session, it doesn't belong in the repo.

**Defensive code for rare server-side conditions gets `# pragma: no cover`, not synthetic tests.** *(from "Real cassettes recorded from real sessions")*
Several code paths handle conditions that are real but impractical to trigger on demand: `AssistantMessage.error` (requires server error/rate limit), missing `ResultMessage.usage` (optional field, rarely None), `ResultMessage.is_error=True` (requires session failure), and `ResultMessage` without preceding `AssistantMessage`. These are small defensive blocks (1-3 lines each) that should keep their `if` guards but not require fabricated test infrastructure. The unit tests for hook functions already cover `post_tool_use_failure_hook` directly.

**Delete all 5 synthetic cassettes and their tests.** *(from "Real cassettes recorded from real sessions", "Defensive code for rare server-side conditions")*
Remove: `error_result.json`, `no_usage_result.json`, `assistant_error.json`, `tool_use_failure.json`, `result_only.json`, and the 5 test functions that use them. The two real cassettes (`basic_conversation.json`, `tool_use_conversation.json`) and the unit tests provide sufficient coverage.

**Add `# pragma: no cover` to the affected defensive branches.** *(from "Defensive code for rare server-side conditions", "Delete all 5 synthetic cassettes")*
Specifically:
- `_record_result`: `if hasattr(msg, 'usage') and msg.usage:` — usage is optional, rarely None
- `_record_result`: `if hasattr(msg, 'total_cost_usd') and msg.total_cost_usd is not None:` — same
- `_record_result`: `if is_error:` — requires session-level failure
- `_TurnTracker.start_turn`: `if error:` for `AssistantMessage.error` — requires server error
- `_TurnTracker.close` / result-only path — ResultMessage without AssistantMessage

**Unit tests for helper functions are unaffected.** *(from "Delete all 5 synthetic cassettes")*
Tests using `Mock` objects for `_content_blocks_to_output_messages`, `_extract_usage`, `_extract_tool_result_text`, hook functions, and hook injection remain as-is. They test our code in isolation with no dependency on cassettes or the SDK transport.
