"""Tests for Tachyon collapsed-stack output -> OTLP profiles export request.

Fixture `tachyon_demo.collapsed` is real output from the Python 3.15
`python -m profiling.sampling run --collapsed -r 2khz` profiler.
"""

from __future__ import annotations

import ctypes
import gzip
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, TypedDict

import pytest
from inline_snapshot import snapshot
from opentelemetry.proto.collector.profiles.v1development.profiles_service_pb2 import (
    ExportProfilesServiceRequest,
)
from opentelemetry.proto.profiles.v1development import profiles_pb2

import logfire
from logfire._internal.config import LogfireConfig
from logfire._internal.profiling.collapsed import parse_collapsed
from logfire._internal.profiling.exporter import ProfilesExporter
from logfire._internal.profiling.otlp import (
    MIN_PROTO_VERSION,
    build_export_request,
    profiles_proto_is_current,
    resource_from_attributes,
)
from logfire._internal.profiling.supervisor import (
    ProfilingSupervisor,
    _allow_child_ptrace,  # pyright: ignore[reportPrivateUsage]
    profiler_available,
)

FIXTURE = Path(__file__).parent / 'profiling_fixtures' / 'tachyon_demo.collapsed'
PROFILE_ID = b'\x11' * 16

# The OTLP profiles schema was renumbered and reshaped in proto v1.10.0, first packaged in
# opentelemetry-proto 1.43.0. Older bindings can't express what we build, so those tests are skipped
# on the CI job that pins an older OpenTelemetry.
requires_current_proto = pytest.mark.skipif(
    not profiles_proto_is_current(), reason=f'needs opentelemetry-proto >= {MIN_PROTO_VERSION}'
)


def _resolve_sample(request: ExportProfilesServiceRequest, sample: profiles_pb2.Sample) -> list[str]:
    """Resolve a sample's stack back to readable `file:func:line`, leaf-first."""
    d = request.dictionary
    out: list[str] = []
    for location_index in d.stack_table[sample.stack_index].location_indices:
        line = d.location_table[location_index].lines[0]
        function = d.function_table[line.function_index]
        filename = d.string_table[function.filename_strindex]
        name = d.string_table[function.name_strindex]
        out.append(f'{filename}:{name}:{line.line}')
    return out


def test_parse_collapsed():
    stacks = list(parse_collapsed(FIXTURE.read_text()))

    assert len(stacks) == snapshot(21)
    assert sum(stack.count for stack in stacks) == snapshot(955)
    # Every line in this fixture is the same single thread.
    assert {stack.thread_id for stack in stacks} == snapshot({57922729})

    # Aggregate samples by innermost (leaf) frame -> a hotspot table.
    by_leaf: dict[tuple[str, int], int] = {}
    for stack in stacks:
        leaf = stack.frames[0]
        key = (leaf.function, leaf.lineno)
        by_leaf[key] = by_leaf.get(key, 0) + stack.count
    assert sorted(by_leaf.items(), key=lambda kv: -kv[1]) == snapshot(
        [(('busy', 7), 632), (('fib', 3), 231), (('busy', 6), 82), (('fib', 2), 10)]
    )


@requires_current_proto
def test_build_export_request():
    request = build_export_request(
        parse_collapsed(FIXTURE.read_text()),
        scope_version='0.spike',
        profile_id=PROFILE_ID,
    )
    d = request.dictionary

    # One Resource -> one Scope -> one Profile.
    [resource_profiles] = request.resource_profiles
    [scope_profiles] = resource_profiles.scope_profiles
    [profile] = scope_profiles.profiles
    assert scope_profiles.scope.name == snapshot('logfire.profiling')

    # Shared dictionary tables, all deduplicated.
    assert (
        len(d.string_table),
        len(d.function_table),
        len(d.location_table),
        len(d.stack_table),
        len(d.attribute_table),
    ) == snapshot((13, 6, 9, 21, 1))

    # The single attribute interned across every sample.
    assert d.string_table[d.attribute_table[0].key_strindex] == snapshot('thread.id')
    assert d.attribute_table[0].value.int_value == snapshot(57922729)

    # sample_type resolves through the string table.
    assert (
        d.string_table[profile.sample_type.type_strindex],
        d.string_table[profile.sample_type.unit_strindex],
    ) == snapshot(('samples', 'count'))

    # The hottest sample, resolved leaf-first.
    hottest = max(profile.samples, key=lambda s: s.values[0])
    assert hottest.values[0] == snapshot(632)
    assert _resolve_sample(request, hottest) == snapshot(
        [
            'prof_demo.py:busy:7',
            'prof_demo.py:main:12',
            'prof_demo.py:<module>:13',
            '<frozen runpy>:_run_code:87',
            '<frozen runpy>:_run_module_as_main:196',
        ]
    )


@requires_current_proto
def test_export_request_round_trips():
    request = build_export_request(parse_collapsed(FIXTURE.read_text()), profile_id=PROFILE_ID)
    reparsed = ExportProfilesServiceRequest()
    reparsed.ParseFromString(request.SerializeToString())
    assert reparsed == request


class _Call(TypedDict):
    url: str
    data: bytes
    headers: dict[str, str]
    timeout: float


class _FakeResponse:
    def __init__(self, status_code: int, text: str = '') -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response
        self.calls: list[_Call] = []

    def post(self, url: str, *, data: bytes, headers: dict[str, str], timeout: float) -> _FakeResponse:
        self.calls.append({'url': url, 'data': data, 'headers': headers, 'timeout': timeout})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


@requires_current_proto
def test_exporter_posts_gzipped_protobuf():
    request = build_export_request(parse_collapsed(FIXTURE.read_text()), profile_id=PROFILE_ID)
    session = _FakeSession(_FakeResponse(200))
    exporter = ProfilesExporter(session, 'https://logfire.example/v1development/profiles')

    assert exporter.export(request) is True
    [call] = session.calls
    assert call['headers'] == snapshot({'Content-Type': 'application/x-protobuf', 'Content-Encoding': 'gzip'})
    # The posted body is gzipped and decodes back to the same request.
    reparsed = ExportProfilesServiceRequest()
    reparsed.ParseFromString(gzip.decompress(call['data']))
    assert reparsed == request


@requires_current_proto
def test_exporter_fails_soft_on_rejection():
    request = build_export_request(parse_collapsed(FIXTURE.read_text()), profile_id=PROFILE_ID)
    exporter = ProfilesExporter(
        _FakeSession(_FakeResponse(503, 'overloaded')), 'https://logfire.example/v1development/profiles'
    )
    with pytest.warns(UserWarning, match='profile export rejected'):
        assert exporter.export(request) is False


ENDPOINT = 'https://logfire.example/v1development/profiles'


def _enable_profiler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the profiler and the current profiles bindings are both available."""
    monkeypatch.setattr('logfire._internal.profiling.supervisor.profiler_available', lambda: True)
    monkeypatch.setattr('logfire._internal.profiling.supervisor.profiles_proto_is_current', lambda: True)


def test_profiler_available_matches_python_version():
    # `profiling.sampling` is stdlib from Python 3.15.
    assert profiler_available() is (sys.version_info >= (3, 15))


def test_supervisor_disabled_without_profiler(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr('logfire._internal.profiling.supervisor.profiler_available', lambda: False)
    supervisor = ProfilingSupervisor(ProfilesExporter(_FakeSession(_FakeResponse(200)), ENDPOINT))
    with pytest.warns(UserWarning, match='Python 3.15'):
        assert supervisor.start() is False
    supervisor.shutdown()  # a no-op, but must be safe even when never started


@requires_current_proto
def test_supervisor_profiles_and_exports(monkeypatch: pytest.MonkeyPatch):
    _enable_profiler(monkeypatch)
    session = _FakeSession(_FakeResponse(200))
    supervisor = ProfilingSupervisor(
        ProfilesExporter(session, ENDPOINT), sample_rate_hz=1000, chunk_duration_seconds=1.0
    )

    fixture_text = FIXTURE.read_text()
    calls: list[int] = []

    def fake_capture(pid: int, duration: float, rate: int) -> str | None:
        calls.append(pid)
        if len(calls) == 1:
            return fixture_text
        supervisor._stop.set()  # pyright: ignore[reportPrivateUsage]  # the loop stops after finishing this chunk
        return ''

    monkeypatch.setattr(supervisor, '_capture_chunk', fake_capture)
    assert supervisor.start() is True
    assert supervisor.start() is True  # starting twice is a no-op
    supervisor.shutdown(timeout=5.0)  # joins the background thread

    # The one chunk was converted and exported.
    [call] = session.calls
    reparsed = ExportProfilesServiceRequest()
    reparsed.ParseFromString(gzip.decompress(call['data']))
    profile = reparsed.resource_profiles[0].scope_profiles[0].profiles[0]
    assert len(profile.samples) == 21
    assert profile.period == 1_000_000  # 1e9 ns / 1000 Hz


def test_supervisor_skips_empty_chunks(monkeypatch: pytest.MonkeyPatch):
    _enable_profiler(monkeypatch)
    session = _FakeSession(_FakeResponse(200))
    supervisor = ProfilingSupervisor(ProfilesExporter(session, ENDPOINT))

    calls: list[int] = []

    def fake_capture(pid: int, duration: float, rate: int) -> str | None:
        calls.append(pid)
        return '' if len(calls) == 1 else None  # an idle chunk, then stop

    monkeypatch.setattr(supervisor, '_capture_chunk', fake_capture)
    supervisor.start()
    supervisor.shutdown(timeout=5.0)

    assert session.calls == []  # an empty chunk is not exported


@requires_current_proto
def test_exporter_fails_soft_on_exception():
    request = build_export_request(parse_collapsed(FIXTURE.read_text()), profile_id=PROFILE_ID)
    exporter = ProfilesExporter(_FakeSession(ConnectionError('boom')), 'https://logfire.example/v1development/profiles')
    with pytest.warns(UserWarning, match='failed to export profile'):
        assert exporter.export(request) is False


@requires_current_proto
def test_resource_attribute_types():
    resource = resource_from_attributes(
        {
            'str': 'value',
            'bool': True,
            'int': 3,
            'float': 1.5,
            'seq': ['a', 2],
            'other': Path('/tmp/x'),
        }
    )
    values = {attribute.key: attribute.value for attribute in resource.attributes}
    assert values['str'].string_value == 'value'
    assert values['bool'].bool_value is True
    assert values['int'].int_value == 3
    assert values['float'].double_value == 1.5
    assert [item.string_value or item.int_value for item in values['seq'].array_value.values] == ['a', 2]
    assert values['other'].string_value == str(Path('/tmp/x'))


def test_supervisor_disabled_with_outdated_proto(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr('logfire._internal.profiling.supervisor.profiler_available', lambda: True)
    monkeypatch.setattr('logfire._internal.profiling.supervisor.profiles_proto_is_current', lambda: False)
    supervisor = ProfilingSupervisor(ProfilesExporter(_FakeSession(_FakeResponse(200)), ENDPOINT))

    with pytest.warns(UserWarning, match=f'needs opentelemetry-proto >= {MIN_PROTO_VERSION}'):
        assert supervisor.start() is False


def test_supervisor_stops_on_unexpected_error(monkeypatch: pytest.MonkeyPatch):
    _enable_profiler(monkeypatch)
    supervisor = ProfilingSupervisor(ProfilesExporter(_FakeSession(_FakeResponse(200)), ENDPOINT))

    def boom(pid: int, duration: float, rate: int) -> str | None:
        raise RuntimeError('kaboom')

    monkeypatch.setattr(supervisor, '_capture_chunk', boom)
    with pytest.warns(UserWarning, match="unexpected error, disabling profiling: RuntimeError\\('kaboom'\\)"):
        assert supervisor.start() is True
        supervisor.shutdown(timeout=5.0)


def _run_fake_profiler(supervisor: ProfilingSupervisor, monkeypatch: pytest.MonkeyPatch, command: list[str]) -> None:
    """Make the supervisor run `command` instead of the real profiler.

    `{out}` in an argument is replaced by the path the profiler is expected to write to.
    """

    def profiler_command(out: Path, pid: int, duration: float, rate: int) -> list[str]:
        return [argument.format(out=out) for argument in command]

    monkeypatch.setattr(supervisor, '_profiler_command', profiler_command)


def _supervisor() -> ProfilingSupervisor:
    return ProfilingSupervisor(ProfilesExporter(_FakeSession(_FakeResponse(200)), ENDPOINT))


def test_capture_chunk_reads_the_profiler_output(monkeypatch: pytest.MonkeyPatch):
    supervisor = _supervisor()
    script = 'import pathlib, sys; pathlib.Path(sys.argv[1]).write_text("tid:1;a.py:f:1 3\\n")'
    _run_fake_profiler(supervisor, monkeypatch, [sys.executable, '-c', script, '{out}'])

    assert supervisor._capture_chunk(os.getpid(), 0.0, 1000) == 'tid:1;a.py:f:1 3\n'  # pyright: ignore[reportPrivateUsage]


def test_capture_chunk_warns_when_the_profiler_writes_nothing(monkeypatch: pytest.MonkeyPatch):
    supervisor = _supervisor()
    script = 'import sys; sys.stderr.write("could not attach to process")'
    _run_fake_profiler(supervisor, monkeypatch, [sys.executable, '-c', script])

    with pytest.warns(UserWarning, match='profiler produced no data. could not attach to process'):
        assert supervisor._capture_chunk(os.getpid(), 0.0, 1000) is None  # pyright: ignore[reportPrivateUsage]


def test_capture_chunk_is_quiet_about_no_data_while_shutting_down(monkeypatch: pytest.MonkeyPatch):
    supervisor = _supervisor()
    _run_fake_profiler(supervisor, monkeypatch, [sys.executable, '-c', ''])
    supervisor.shutdown()  # sets the stop flag without ever having started

    assert supervisor._capture_chunk(os.getpid(), 0.0, 1000) is None  # pyright: ignore[reportPrivateUsage]


def test_capture_chunk_warns_when_the_profiler_cannot_run(monkeypatch: pytest.MonkeyPatch):
    supervisor = _supervisor()
    _run_fake_profiler(supervisor, monkeypatch, [str(Path(__file__).parent / 'not-a-real-executable')])

    with pytest.warns(UserWarning, match='could not run the profiler'):
        assert supervisor._capture_chunk(os.getpid(), 0.0, 1000) is None  # pyright: ignore[reportPrivateUsage]


def test_capture_chunk_kills_a_profiler_that_overruns(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr('logfire._internal.profiling.supervisor._SUBPROCESS_TIMEOUT_GRACE_SECONDS', 0.5)
    supervisor = _supervisor()
    _run_fake_profiler(supervisor, monkeypatch, [sys.executable, '-c', 'import time; time.sleep(30)'])

    with pytest.warns(UserWarning, match='profiler subprocess timed out'):
        assert supervisor._capture_chunk(os.getpid(), 0.0, 1000) is None  # pyright: ignore[reportPrivateUsage]


def test_allow_child_ptrace_is_a_no_op_off_linux(monkeypatch: pytest.MonkeyPatch):
    def fail(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError('should not touch libc off Linux')

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(ctypes, 'CDLL', fail)
    _allow_child_ptrace()


def test_allow_child_ptrace_calls_prctl_on_linux(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[Any, ...]] = []

    class FakeLibc:
        def prctl(self, *args: Any) -> int:
            calls.append(args)
            return 0

    def fake_cdll(*args: Any, **kwargs: Any) -> FakeLibc:
        return FakeLibc()

    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(ctypes, 'CDLL', fake_cdll)
    _allow_child_ptrace()

    # PR_SET_PTRACER, PR_SET_PTRACER_ANY, then the three unused prctl arguments.
    [(option, ptracer, *rest)] = calls
    assert (option, ptracer.value, rest) == (0x59616D61, ctypes.c_ulong(-1).value, [0, 0, 0])


def test_allow_child_ptrace_ignores_a_hardened_kernel(monkeypatch: pytest.MonkeyPatch):
    def raise_os_error(*args: Any, **kwargs: Any) -> None:
        raise OSError('no libc for you')

    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(ctypes, 'CDLL', raise_os_error)
    _allow_child_ptrace()  # must not raise


def wait_for_check_token_thread():
    for thread in threading.enumerate():
        if thread.name == 'check_logfire_token':  # pragma: no cover
            thread.join()


def test_configure_wires_profiling(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', lambda *args: None)  # type: ignore
    started: list[ProfilingSupervisor] = []

    def start(self: ProfilingSupervisor) -> bool:
        started.append(self)
        return True

    monkeypatch.setattr(ProfilingSupervisor, 'start', start)

    logfire_instance = logfire.configure(
        local=True,
        token='pylf_v1_us_token',
        send_to_logfire=True,
        console=False,
        metrics=False,
        profiling=True,
    )
    wait_for_check_token_thread()

    [supervisor] = started
    assert logfire_instance.config._profiling_supervisor is supervisor  # pyright: ignore[reportPrivateUsage]
    # Profiles go to the same region as the other signals, authenticated with the same token.
    exporter = supervisor._exporter  # pyright: ignore[reportPrivateUsage]
    assert exporter._endpoint == 'https://logfire-us.pydantic.dev/v1development/profiles'  # pyright: ignore[reportPrivateUsage]
    assert exporter._headers['Authorization'] == 'pylf_v1_us_token'  # pyright: ignore[reportPrivateUsage]

    logfire_instance.shutdown(flush=False)
    assert logfire_instance.config._profiling_supervisor is None  # pyright: ignore[reportPrivateUsage]


def test_reconfiguring_replaces_the_profiling_supervisor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', lambda *args: None)  # type: ignore
    shutdowns: list[ProfilingSupervisor] = []

    def start(self: ProfilingSupervisor) -> bool:
        return True

    def shutdown(self: ProfilingSupervisor, timeout: float = 5.0) -> None:
        shutdowns.append(self)

    monkeypatch.setattr(ProfilingSupervisor, 'start', start)
    monkeypatch.setattr(ProfilingSupervisor, 'shutdown', shutdown)

    kwargs: dict[str, Any] = dict(
        token='pylf_v1_us_token', send_to_logfire=True, console=False, metrics=False, profiling=True
    )
    logfire.configure(**kwargs)
    first = logfire.DEFAULT_LOGFIRE_INSTANCE.config._profiling_supervisor  # pyright: ignore[reportPrivateUsage]
    logfire.configure(**kwargs)
    second = logfire.DEFAULT_LOGFIRE_INSTANCE.config._profiling_supervisor  # pyright: ignore[reportPrivateUsage]
    wait_for_check_token_thread()

    assert first is not None and second is not None and first is not second
    assert shutdowns == [first]


def test_configure_profiling_without_a_token_warns():
    with pytest.warns(UserWarning, match='Logfire profiling needs a Logfire token'):
        logfire_instance = logfire.configure(local=True, send_to_logfire=False, console=False, profiling=True)
    assert logfire_instance.config._profiling_supervisor is None  # pyright: ignore[reportPrivateUsage]


def test_parse_collapsed_tolerates_odd_lines():
    stacks = list(
        parse_collapsed(
            '\n'.join(
                [
                    '',  # blank
                    '   ',  # whitespace only
                    'a header line',  # no sample count
                    '42',  # a count with no stack
                    'a.py:f:1;b.py:g:2 5',  # no thread id
                    'tid:nope;a.py:f:1 6',  # unparseable thread id
                    'tid:7;a.py:f:oops;; 8',  # unparseable line number, and an empty frame
                ]
            )
        )
    )

    assert [
        (stack.thread_id, [(frame.function, frame.lineno) for frame in stack.frames], stack.count) for stack in stacks
    ] == snapshot(
        [
            (0, [('g', 2), ('f', 1)], 5),
            (0, [('f', 1)], 6),
            (7, [('f', 0)], 8),
        ]
    )


@requires_current_proto
def test_build_export_request_without_thread_ids():
    resource = resource_from_attributes({'service.name': 'my-service'})
    request = build_export_request(
        parse_collapsed('a.py:f:1;b.py:g:2 5\na.py:f:1;b.py:g:2 7'), resource=resource, profile_id=PROFILE_ID
    )

    [resource_profiles] = request.resource_profiles
    assert [attribute.key for attribute in resource_profiles.resource.attributes] == ['service.name']
    [profile] = resource_profiles.scope_profiles[0].profiles
    # The two lines share a stack, so they share the one interned stack-table entry.
    assert [sample.stack_index for sample in profile.samples] == [0, 0]
    assert [sample.values[0] for sample in profile.samples] == [5, 7]
    assert len(request.dictionary.stack_table) == 1
    # Without a thread id there's nothing to attribute the samples with.
    assert [list(sample.attribute_indices) for sample in profile.samples] == [[], []]
    assert list(request.dictionary.attribute_table) == []


def test_profiler_available_survives_a_broken_import_system(monkeypatch: pytest.MonkeyPatch):
    def raise_value_error(name: str) -> None:
        raise ValueError('__spec__ is not set')

    monkeypatch.setattr('importlib.util.find_spec', raise_value_error)
    assert profiler_available() is False


def test_shutdown_terminates_a_running_profiler(monkeypatch: pytest.MonkeyPatch):
    _enable_profiler(monkeypatch)
    supervisor = _supervisor()
    _run_fake_profiler(supervisor, monkeypatch, [sys.executable, '-c', 'import time; time.sleep(30)'])
    running = threading.Event()
    capture_chunk = supervisor._capture_chunk  # pyright: ignore[reportPrivateUsage]

    def capture(pid: int, duration: float, rate: int) -> str | None:
        running.set()
        return capture_chunk(pid, duration, rate)

    monkeypatch.setattr(supervisor, '_capture_chunk', capture)
    assert supervisor.start() is True
    assert running.wait(timeout=10)
    while supervisor._proc is None:  # pragma: no cover  # pyright: ignore[reportPrivateUsage]
        time.sleep(0.01)

    # Terminating the profiler leaves no output, which is expected during shutdown and so isn't warned about.
    supervisor.shutdown(timeout=10)
    assert supervisor._thread is None  # pyright: ignore[reportPrivateUsage]


def test_profiler_command_targets_this_process():
    supervisor = ProfilingSupervisor(
        ProfilesExporter(_FakeSession(_FakeResponse(200)), ENDPOINT), sample_rate_hz=2000, chunk_duration_seconds=30.0
    )
    command = supervisor._profiler_command(Path('/tmp/chunk.collapsed'), 123, 30.0, 2000)  # pyright: ignore[reportPrivateUsage]

    assert command[:2] == [sys.executable, '-m']
    assert command[2:] == snapshot(
        [
            'profiling.sampling',
            'attach',
            '--collapsed',
            '--all-threads',
            '-d',
            '30.0',
            '-r',
            '2000',
            '-o',
            '/tmp/chunk.collapsed',
            '123',
        ]
    )
