"""Run the Python sampling profiler against this process and export OTLP profiles.

This drives the Python 3.15 `profiling.sampling` (Tachyon) profiler as a child
process that attaches back to this one, in repeated fixed-duration chunks. Each
chunk's collapsed-stack output is converted to OTLP profiles and exported.

Everything degrades gracefully: if the profiler is unavailable (Python < 3.15)
or the platform / permissions do not allow attaching, profiling is disabled
with a warning and the rest of Logfire is unaffected. Nothing here raises.

Profiling does not follow `os.fork()`: the background thread doesn't survive a
fork, so a forked worker isn't profiled unless it configures Logfire itself.
"""

from __future__ import annotations

import ctypes
import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from pathlib import Path

from opentelemetry.proto.resource.v1.resource_pb2 import Resource

from .collapsed import parse_collapsed
from .exporter import ProfilesExporter
from .otlp import MIN_PROTO_VERSION, build_export_request, profiles_proto_is_current

# prctl(PR_SET_PTRACER, <pid>) lets that one process ptrace us without root -
# which is what the profiler child needs on Linux under the common Yama
# `ptrace_scope=1`. The constant 0x59616d61 spells "Yama". Naming a pid rather
# than PR_SET_PTRACER_ANY keeps the exemption as narrow as possible, and pid 0
# revokes it again.
_PR_SET_PTRACER = 0x59616D61
_PTRACER_NONE = 0

_NS_PER_SECOND = 1_000_000_000

# How long after its requested duration the profiler subprocess is given to finish.
_SUBPROCESS_TIMEOUT_GRACE_SECONDS = 30.0


def profiler_available() -> bool:
    """Return True if the `profiling.sampling` profiler is importable (Python 3.15+)."""
    try:
        return importlib.util.find_spec('profiling.sampling') is not None
    except (ImportError, ValueError):
        return False


def _allow_ptrace_by(pid: int) -> None:
    """Best-effort: let process `pid` (`_PTRACER_NONE` to revoke) ptrace this one (Linux / Yama only)."""
    if not sys.platform.startswith('linux'):
        return  # macOS / Windows need elevation instead; handled by failing soft
    try:
        libc = ctypes.CDLL(None, use_errno=True)  # not "libc.so.6" - works on musl too
        libc.prctl(_PR_SET_PTRACER, pid, 0, 0, 0)
    except (OSError, AttributeError, ValueError):
        pass  # hardened kernel / no prctl - the profiler simply fails its first chunk


class ProfilingSupervisor:
    """Continuously profiles this process in a background thread.

    Each cycle runs the profiler for `chunk_duration_seconds`, converts the
    result to OTLP profiles and hands it to `exporter`.
    """

    def __init__(
        self,
        exporter: ProfilesExporter,
        *,
        resource: Resource | None = None,
        sample_rate_hz: int = 1000,
        chunk_duration_seconds: float = 60.0,
        scope_version: str = '',
    ) -> None:
        self._exporter = exporter
        self._resource = resource
        self._sample_rate_hz = sample_rate_hz
        self._chunk_duration = chunk_duration_seconds
        self._scope_version = scope_version
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # `_proc` is shared with whoever calls `shutdown`, so `_lock` guards it. Holding the lock
        # across the spawn is what stops a profiler from starting after a shutdown terminated it.
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None

    def start(self) -> bool:
        """Start background profiling. Returns False (with a warning) if unsupported."""
        if not profiler_available():
            warnings.warn('Logfire profiling needs Python 3.15+ (the `profiling.sampling` module); disabled.')
            return False
        if not profiles_proto_is_current():
            # Serializing with older bindings would produce profiles that consumers silently misread.
            warnings.warn(
                f'Logfire profiling needs opentelemetry-proto >= {MIN_PROTO_VERSION} '
                'for the current OTLP profiles schema; disabled.'
            )
            return False
        if self._thread is not None:
            return True  # already running
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='logfire-profiling', daemon=True)
        self._thread.start()
        return True

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop profiling, kill the profiler subprocess and join the background thread."""
        self._stop.set()
        with self._lock:
            proc = self._proc
            if proc is not None:
                proc.terminate()  # a no-op if it has already exited
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
            if not thread.is_alive():
                # Only forget a thread that has actually stopped, so that a restart can't leave
                # two of them profiling (and exporting) at once.
                self._thread = None

    def _run(self) -> None:
        pid = os.getpid()
        while not self._stop.is_set():
            try:
                keep_going = self._run_once(pid)
            except Exception as exc:
                warnings.warn(f'Logfire profiling: unexpected error, disabling profiling: {exc!r}')
                return
            if not keep_going:
                # A failed chunk is almost always permanent (permissions, platform),
                # so stop rather than spin and emit the same warning forever.
                return

    def _run_once(self, pid: int) -> bool:
        """Capture, convert and export one profiling chunk. Returns False on failure."""
        start_time = time.time_ns()
        collapsed = self._capture_chunk(pid, self._chunk_duration, self._sample_rate_hz)
        if collapsed is None:
            return False
        if not collapsed.strip():
            return True  # nothing sampled this chunk (e.g. an idle process) - keep going

        request = build_export_request(
            parse_collapsed(collapsed),
            resource=self._resource,
            scope_version=self._scope_version,
            period_type='cpu',
            period_unit='nanoseconds',
            period=_NS_PER_SECOND // self._sample_rate_hz,
            start_time_unix_nano=start_time,
            duration_nano=int(self._chunk_duration * _NS_PER_SECOND),
        )
        self._exporter.export(request)  # fails soft internally
        return True

    def _capture_chunk(self, pid: int, duration: float, rate: int) -> str | None:
        """Run one profiler subprocess; return collapsed-stack text, or None on failure.

        The profiler exits 0 even when it cannot read the target's memory, so
        success is judged by whether non-empty output was actually written.
        """
        with tempfile.TemporaryDirectory(prefix='logfire-profiling-') as tmp:
            out = Path(tmp) / 'chunk.collapsed'
            try:
                with self._lock:
                    if self._stop.is_set():
                        return None  # shutting down: don't start a profiler nobody will terminate
                    cmd = self._profiler_command(out, pid, duration, rate)
                    self._proc = proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            except OSError as exc:
                warnings.warn(f'Logfire profiling: could not run the profiler: {exc!r}')
                return None

            # Grant ptrace only to this profiler, only while it runs.
            _allow_ptrace_by(proc.pid)
            try:
                _, stderr = proc.communicate(timeout=duration + _SUBPROCESS_TIMEOUT_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                warnings.warn('Logfire profiling: profiler subprocess timed out.')
                return None
            finally:
                _allow_ptrace_by(_PTRACER_NONE)
                with self._lock:
                    self._proc = None

            if not out.exists() or out.stat().st_size == 0:
                if not self._stop.is_set():  # an empty file during shutdown is expected
                    warnings.warn(f'Logfire profiling: profiler produced no data. {stderr.strip()[:300]}')
                return None
            return out.read_text()

    def _profiler_command(self, out: Path, pid: int, duration: float, rate: int) -> list[str]:
        """The command line running the profiler against `pid`, writing collapsed stacks to `out`."""
        return [
            sys.executable, '-m', 'profiling.sampling', 'attach',
            '--collapsed', '--all-threads',
            '-d', str(duration), '-r', str(rate),
            '-o', str(out), str(pid),
        ]  # fmt: skip
