#!/usr/bin/env python3
"""Fake claude process for cassette-based testing.

Operates in two modes:
- **replay** (default): Reads a cassette file and replays recorded stdout
  messages, consuming stdin messages at the correct protocol points.
- **record**: Spawns the real `claude` CLI as a child process, proxies
  stdin/stdout between the SDK and the real process, and tees every
  message to a cassette file.

The cassette path and mode are controlled by environment variables:
- CASSETTE_PATH: path to the cassette JSON file (required)
- CASSETTE_MODE: "replay" (default) or "record"
- REAL_CLAUDE_PATH: path to the real claude CLI (required for record mode)

The SDK invokes this script via `ClaudeAgentOptions(cli_path=...)`.
All CLI arguments are accepted and ignored in replay mode (the SDK passes
flags like --output-format, --verbose, etc.).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

# cast is used inside functions, but __future__.annotations makes it lazy.
# We need it available at runtime for the recursive helpers.
from typing import cast


def main() -> None:
    # Handle version check: the SDK runs `cli_path -v` before the main session.
    if '-v' in sys.argv:
        mode = os.environ.get('CASSETTE_MODE', 'replay')
        if mode == 'record':
            # In record mode, proxy -v to the real CLI for an accurate version
            real_claude = os.environ.get('REAL_CLAUDE_PATH', '')
            if real_claude:
                result = subprocess.run([real_claude, '-v'], capture_output=True, text=True, timeout=10)
                print(result.stdout.strip())
                sys.exit(result.returncode)
        # In replay mode, read version from the cassette metadata
        cassette_path = os.environ.get('CASSETTE_PATH', '')
        if cassette_path and os.path.exists(cassette_path):
            with open(cassette_path) as f:
                cassette = json.load(f)
            version = cassette.get('metadata', {}).get('cli_version', '1.0.100')
        else:
            version = '1.0.100'
        print(version)
        return

    mode = os.environ.get('CASSETTE_MODE', 'replay')
    cassette_path = os.environ.get('CASSETTE_PATH', '')

    if not cassette_path:
        print('CASSETTE_PATH environment variable is required', file=sys.stderr)
        sys.exit(1)

    if mode == 'record':
        _record(cassette_path)
    else:
        _replay(cassette_path)


def _replay(cassette_path: str) -> None:
    """Replay a recorded cassette through stdin/stdout.

    The cassette is a sequence of JSON messages alternating between 'send' (SDK->CLI)
    and 'recv' (CLI->SDK). We walk through them in order:
    - For 'recv' entries, write the recorded message to stdout (the SDK reads it).
    - For 'send' entries, read a line from stdin (the SDK wrote it) and discard it.

    **ID remapping**: The SDK generates fresh random IDs (request_id, session_id, etc.)
    each time it runs — these won't match the IDs in the cassette. If we replay the
    cassette's original IDs, the SDK will never see a response matching the request_id
    it sent, and it will hang forever. To fix this, we:
    1. Compare each 'send' message from the SDK against the corresponding recorded
       'send' message to learn which IDs have changed (e.g., recorded request_id
       "req_1_abc" is now "req_1_xyz").
    2. Before writing each 'recv' message to stdout, replace any recorded IDs with
       the live IDs so the SDK sees its own IDs reflected back.

    This remapping is specific to the subprocess replay approach. A custom in-process
    Transport (the mock approach) wouldn't need it because it constructs response
    objects directly in Python and can use whatever IDs the SDK provides.
    """
    debug = os.environ.get('FAKE_CLAUDE_DEBUG', '')

    with open(cassette_path) as f:
        cassette = json.load(f)

    messages = cassette['messages']
    i = 0

    # Maps recorded IDs to live IDs (e.g., recorded "req_1_abc" -> live "req_1_xyz")
    id_map: dict[str, str] = {}

    def _patch_ids(msg: object) -> object:
        """Recursively replace all recorded ID strings with their live equivalents."""
        if isinstance(msg, dict):
            return {k: _patch_ids(v) for k, v in cast(dict[str, object], msg).items()}
        if isinstance(msg, list):
            return [_patch_ids(item) for item in cast(list[object], msg)]
        if isinstance(msg, str) and msg in id_map:
            return id_map[msg]
        return msg

    # Only remap string values under these JSON keys — avoids accidentally rewriting
    # user prompts or other content that happens to differ.
    _ID_KEYS = frozenset(
        {
            'request_id',
            'session_id',
            'uuid',
            'id',
            'hookCallbackIds',  # list of strings, handled via recursion
        }
    )

    def _learn_ids(recorded: object, live: object, *, key: str | None = None) -> None:
        """Walk two message trees in parallel, recording ID differences.

        Recursively descends dicts/lists. When both trees have a string at
        the same path and the path's key is in _ID_KEYS, records the mapping
        from the recorded value to the live value.
        """
        if isinstance(recorded, dict) and isinstance(live, dict):
            rec_dict = cast(dict[str, object], recorded)
            live_dict = cast(dict[str, object], live)
            for k in rec_dict:
                if k in live_dict:
                    _learn_ids(rec_dict[k], live_dict[k], key=k)
        elif isinstance(recorded, list) and isinstance(live, list):
            for rec_item, live_item in zip(cast(list[object], recorded), cast(list[object], live)):
                _learn_ids(rec_item, live_item, key=key)
        elif key in _ID_KEYS and isinstance(recorded, str) and isinstance(live, str) and recorded != live:
            id_map[recorded] = live

    while i < len(messages):
        entry = messages[i]

        if entry['direction'] == 'recv':
            # Replay a CLI->SDK message, substituting any remapped IDs
            msg = _patch_ids(entry['message'])
            line = json.dumps(msg) + '\n'
            if debug:
                print(f'[fake_claude] SEND stdout: {line.strip()[:120]}', file=sys.stderr)
            sys.stdout.write(line)
            sys.stdout.flush()
            i += 1

        elif entry['direction'] == 'send':
            # Consume a SDK->CLI message and learn any new ID mappings from it
            if debug:
                print(f'[fake_claude] WAIT stdin (entry {i})...', file=sys.stderr)
            line = sys.stdin.readline()
            if not line:
                if debug:
                    print('[fake_claude] stdin closed', file=sys.stderr)
                break
            if debug:
                print(f'[fake_claude] GOT stdin: {line.strip()[:120]}', file=sys.stderr)
            # Learn ID mappings from this message
            try:
                live_msg = json.loads(line)
                _learn_ids(entry['message'], live_msg)
            except json.JSONDecodeError:
                pass
            i += 1


def _record(cassette_path: str) -> None:
    """Record a real session by proxying between SDK and real claude CLI."""
    real_claude = os.environ.get('REAL_CLAUDE_PATH', '')
    if not real_claude:
        print('REAL_CLAUDE_PATH environment variable is required for record mode', file=sys.stderr)
        sys.exit(1)

    # Build the command: replace argv[0] with the real claude path,
    # keep all other arguments the SDK passed
    cmd = [real_claude] + sys.argv[1:]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    messages: list[dict[str, object]] = []

    # Detect real CLI version by running -v
    try:
        ver_result = subprocess.run([real_claude, '-v'], capture_output=True, text=True, timeout=10)
        cli_version = ver_result.stdout.strip() or '1.0.100'
    except Exception:
        cli_version = '1.0.100'

    def _proxy_stderr() -> None:
        """Pass stderr through without recording."""
        assert proc.stderr is not None
        for line in proc.stderr:
            sys.stderr.buffer.write(line)
            sys.stderr.buffer.flush()

    stderr_thread = threading.Thread(target=_proxy_stderr, daemon=True)
    stderr_thread.start()

    def _proxy_stdin() -> None:
        """Read from our stdin (SDK), forward to real process, record as 'send'."""
        assert proc.stdin is not None
        for line in sys.stdin:
            messages.append({'direction': 'send', 'message': json.loads(line)})
            proc.stdin.write(line.encode() if isinstance(line, str) else line)
            proc.stdin.flush()
        # stdin closed — close the child's stdin too
        proc.stdin.close()

    stdin_thread = threading.Thread(target=_proxy_stdin, daemon=True)
    stdin_thread.start()

    # Read stdout from real process, forward to SDK, record as 'recv'
    assert proc.stdout is not None
    for line_bytes in proc.stdout:
        line = line_bytes.decode()
        try:
            msg = json.loads(line)
            messages.append({'direction': 'recv', 'message': msg})
        except json.JSONDecodeError:
            # Non-JSON output — forward but don't record
            pass
        sys.stdout.write(line)
        sys.stdout.flush()

    proc.wait()
    stdin_thread.join(timeout=2)

    # Write cassette
    cassette = {
        'metadata': {
            'cli_version': cli_version,
        },
        'messages': messages,
    }
    with open(cassette_path, 'w') as f:
        json.dump(cassette, f, indent=2)
        f.write('\n')

    sys.exit(proc.returncode or 0)


if __name__ == '__main__':
    main()
