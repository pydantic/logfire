"""Parse Tachyon (`python -m profiling.sampling ... --collapsed`) output.

The collapsed-stack format emitted by the Python 3.15 sampling profiler is one
folded stack per line::

    tid:<thread_id>;<frame>;<frame>;...;<frame> <count>

Frames are ordered outermost-first (the leaf/innermost frame is last). Each
frame is ``<filename>:<function>:<lineno>``. ``<count>`` is the number of
samples that landed on that exact stack. The format carries a thread id per
line but no per-sample timestamps and no sample rate.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    """A single resolved stack frame."""

    filename: str
    function: str
    lineno: int


@dataclass
class FoldedStack:
    """One folded stack: a unique call stack and how many samples hit it."""

    thread_id: int
    # Ordered leaf-first (innermost frame at index 0) to match the
    # pprof/OTLP `Sample` location ordering.
    frames: list[Frame]
    count: int


def _parse_frame(token: str) -> Frame:
    # rsplit so a Windows drive letter (or any ':' in the path) survives:
    # only the final two ':' separate function name and line number.
    filename, function, lineno = token.rsplit(':', 2)
    try:
        line = int(lineno)
    except ValueError:
        line = 0
    return Frame(filename=filename, function=function, lineno=line)


def parse_collapsed(text: str) -> Iterator[FoldedStack]:
    """Yield a `FoldedStack` for each non-empty line of collapsed-stack text."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        stack_part, _, count_part = line.rpartition(' ')
        if not stack_part:
            continue
        try:
            count = int(count_part)
        except ValueError:
            # Not a folded-stack line (e.g. a stray header) - skip it.
            continue

        tokens = stack_part.split(';')
        thread_id = 0
        if tokens and tokens[0].startswith('tid:'):
            try:
                thread_id = int(tokens[0][len('tid:') :])
            except ValueError:
                thread_id = 0
            tokens = tokens[1:]

        frames = [_parse_frame(token) for token in tokens if token]
        frames.reverse()  # outermost-first on the wire -> leaf-first model
        yield FoldedStack(thread_id=thread_id, frames=frames, count=count)
