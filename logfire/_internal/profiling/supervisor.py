"""Run the Python sampling profiler against this process and export OTLP profiles.

This drives the Python 3.15 `profiling.sampling` (Tachyon) profiler as a child
process that attaches back to this one, in repeated fixed-duration chunks. Each
chunk's collapsed-stack output is converted to OTLP profiles and exported.

Everything degrades gracefully: if the profiler is unavailable (Python < 3.15)
or the platform / permissions do not allow attaching, profiling is disabled
with a warning and the rest of Logfire is unaffected. Nothing here raises.
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
from .otlp import build_export_request

# prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY) lets a same-uid descendant ptrace
# us without root - which is what the profiler child needs on Linux under the
# common Yama `ptrace_scope=1`. The constant 0x59616d61 spells "Yama".
_PR_SET_PTRACER = 0x59616D61
_PR_SET_PTRACER_ANY = ctypes.c_ulong(-1)

_NS_PER_SECOND = 1_000_000_000


def profiler_available() -> bool:
    """Return True if the `profiling.sampling` profiler is importable (Python 3.15+)."""
    try:
        return importlib.util.find_spec('profiling.sampling') is not None
    except (ImportError, ValueError):
        return False


def _allow_child_ptrace() -> None:
    """Best-effort: let a child process ptrace this one (Linux / Yama only)."""
    if not sys.platform.startswith('linux'):
        return  # macOS / Windows need elevation instead; handled by failing soft
    try:
        libc = ctypes.CDLL(None, use_errno=True)  # not "libc.so.6" - works on musl too
        libc.prctl(_PR_SET_PTRACER, _PR_SET_PTRACER_ANY, 0, 0, 0)
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
        self._proc: subprocess.Popen[str] | None = None

    def start(self) -> bool:
        """Start background profiling. Returns False (with a warning) if unsupported."""
        if not profiler_available():
            warnings.warn('Logfire profiling needs Python 3.15+ (the `profiling.sampling` module); disabled.')
            return False
        if self._thread is not None:
            return True  # already running
        _allow_child_ptrace()
        self._thread = threading.Thread(target=self._run, name='logfire-profiling', daemon=True)
        self._thread.start()
        return True

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop profiling, kill the profiler subprocess and join the background thread."""
        self._stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        pid = os.getpid()
        while not self._stop.is_set():
            if not self._run_once(pid):
                # A failed chunk is almost always permanent (permissions, platform),
                # so stop rather than spin and emit the same warning forever.
                break

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
            cmd = [
                sys.executable, '-m', 'profiling.sampling', 'attach',
                '--collapsed', '--all-threads',
                '-d', str(duration), '-r', str(rate),
                '-o', str(out), str(pid),
            ]  # fmt: skip
            stderr = ''
            try:
                self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                _, stderr = self._proc.communicate(timeout=duration + 30)
            except subprocess.TimeoutExpired:
                self._kill_proc()
                warnings.warn('Logfire profiling: profiler subprocess timed out.')
                return None
            except OSError as exc:
                warnings.warn(f'Logfire profiling: could not run the profiler: {exc!r}')
                return None
            finally:
                self._proc = None

            if not out.exists() or out.stat().st_size == 0:
                if not self._stop.is_set():  # an empty file during shutdown is expected
                    warnings.warn(f'Logfire profiling: profiler produced no data. {stderr.strip()[:300]}')
                return None
            return out.read_text()

    def _kill_proc(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.communicate()
