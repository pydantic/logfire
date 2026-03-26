# Cassette-Based Testing for Claude Agent SDK Integration

**Tests must exercise the real SDK client against realistic I/O, not a hand-crafted mock transport.**
The current `MockTransport` reimplements SDK protocol logic (handshakes, hook callback dispatch, event synchronization). This means tests validate the mock's behavior, not real behavior — spans produced in tests don't match what the instrumentation produces against a real `claude` process. We need a VCR-like record/replay approach.

**The SDK's `SubprocessCLITransport` stays in the loop during tests.** *(from "Tests must exercise the real SDK")*
We don't replace the transport layer. Instead, we replace what's on the other end of the pipes — the `claude` process itself. The SDK's `ClaudeAgentOptions` has a `cli_path` parameter that controls which executable is spawned. Tests pass `cli_path=` pointing to a fake process that replays recorded I/O. This means the real transport's pipe handling, JSON parsing, and process lifecycle code all execute during tests.

**A single Python script (`fake_claude.py`) acts as both recorder and replayer.** *(from "The SDK's SubprocessCLITransport stays in the loop")*
The script lives in the test fixtures directory. It operates in two modes controlled by a CLI flag or environment variable:

- **Record mode**: The script spawns the real `claude` process as a child, proxies stdin/stdout between the SDK and the real process, and tees every message (with direction and ordering) to a cassette file. When the real process exits, the cassette is finalized.
- **Replay mode**: No real process is spawned. The script reads a cassette file and replays the recorded stdout messages, consuming stdin messages at the correct points in the sequence to maintain protocol timing.

**The version check must be handled.** *(from "A single Python script acts as both recorder and replayer")*
Before spawning the main conversation, `SubprocessCLITransport` runs `cli_path -v` to check the Claude Code version. In record mode, the proxy forwards this to the real CLI. In replay mode, the script returns a hardcoded version string (recorded in the cassette metadata) and exits when invoked with `-v`.

**Cassette files are JSON arrays of ordered message entries.** *(from "A single Python script acts as both recorder and replayer")*
Each entry is `{"direction": "send" | "recv", "message": <JSON object>}`. `send` means the SDK wrote to the process's stdin; `recv` means the process wrote to stdout. The array preserves the exact ordering from the real session. A metadata header (first element or a wrapper object) stores the CLI version string and any other session metadata.

**Replay respects protocol timing via send/recv alternation.** *(from "Cassette files are JSON arrays", "The SDK's SubprocessCLITransport stays in the loop")*
The real protocol is interactive — the subprocess sends a hook callback request, then blocks reading stdin until the SDK responds. The replay script mirrors this: it writes all `recv` entries to stdout until it hits a `send` entry, then reads one line from stdin (the SDK's response), then continues. This keeps the SDK's internal state machine synchronized without any sleep or timing heuristics.

**Cassette files live alongside tests in a `cassettes/` directory.** *(from "Cassette files are JSON arrays")*
Following the VCR convention. For example, `tests/otel_integrations/cassettes/basic_conversation.json`. Each test that needs a cassette references it by name.

**A pytest fixture provides the cassette-backed client.** *(from "The SDK's SubprocessCLITransport stays in the loop", "Cassette files live alongside tests")*
A fixture (e.g., `cassette_client` or a `@pytest.mark.cassette("name")` marker) constructs a `ClaudeSDKClient` with `cli_path` pointing to `fake_claude.py` in replay mode, passing the cassette path. Tests call `client.connect()`, `client.query()`, `client.receive_response()` as normal. The fixture handles cleanup.

**Recording is triggered by a pytest flag, like VCR.** *(from "A single Python script acts as both recorder and replayer", "A pytest fixture provides the cassette-backed client")*
Running `pytest --record-cassettes` (or a per-test `--record-mode=rewrite` flag) switches the fixture to record mode: `cli_path` points to `fake_claude.py` in record mode, which proxies to the real `claude` CLI. The cassette file is written on teardown. Subsequent runs without the flag use replay mode. Tests that don't have a cassette file yet fail with a clear error message pointing to the record command.

**The existing `MockTransport` and its tests are replaced.** *(from "Tests must exercise the real SDK")*
Once cassette-based tests cover the same scenarios, the `MockTransport` class and all the hand-crafted message fixtures (`ASSISTANT_HELLO`, `ASSISTANT_TOOL_USE`, etc.) are removed. Unit tests for pure helper functions (like `_extract_usage`, `_content_blocks_to_output_messages`) that don't need the SDK at all can remain as-is.

**Record mode requires a working `claude` CLI with valid credentials.** *(from "Recording is triggered by a pytest flag")*
This is an explicit trade-off. Recording cassettes requires a real Claude session (which costs money). But it only needs to happen once per test scenario, and the cassettes are committed to the repo. CI always runs in replay mode. A developer re-records only when the test scenario changes or the SDK protocol evolves.

**Cassette drift detection is optional but desirable.** *(from "Replay respects protocol timing", "Record mode requires a working claude CLI")*
During replay, the script can optionally compare the SDK's stdin messages against the recorded `send` entries. Mismatches indicate that the SDK's behavior has changed (e.g., a new field in the init handshake). This is a warning, not a hard failure — minor drift in fields we don't care about shouldn't break tests. The comparison can be controlled by a strictness flag.

**The proxy script handles stderr passthrough.** *(from "A single Python script acts as both recorder and replayer")*
The real `claude` process writes debug info to stderr. In record mode, the proxy passes stderr through (or captures it separately). In replay mode, stderr is not replayed — it's not part of the protocol. The cassette only stores stdin/stdout messages.
