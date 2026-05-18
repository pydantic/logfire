"""Tests for Tachyon collapsed-stack output -> OTLP profiles export request.

Fixture `tachyon_demo.collapsed` is real output from the Python 3.15
`python -m profiling.sampling run --collapsed -r 2khz` profiler.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import pytest
from inline_snapshot import snapshot

from logfire._internal.profiling._proto import profiles_pb2
from logfire._internal.profiling._proto.profiles_service_pb2 import ExportProfilesServiceRequest
from logfire._internal.profiling.collapsed import parse_collapsed
from logfire._internal.profiling.exporter import ProfilesExporter
from logfire._internal.profiling.otlp import build_export_request

FIXTURE = Path(__file__).parent / 'profiling_fixtures' / 'tachyon_demo.collapsed'
PROFILE_ID = b'\x11' * 16


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


def test_exporter_posts_gzipped_protobuf():
    request = build_export_request(parse_collapsed(FIXTURE.read_text()), profile_id=PROFILE_ID)
    session = _FakeSession(_FakeResponse(200))
    exporter = ProfilesExporter(session, 'https://logfire.example/v1development/profiles')

    assert exporter.export(request) is True
    [call] = session.calls
    assert call['headers'] == snapshot({'Content-Type': 'application/x-protobuf', 'Content-Encoding': 'gzip'})
    # The posted body is gzipped and decodes back to the same request.
    import gzip

    reparsed = ExportProfilesServiceRequest()
    reparsed.ParseFromString(gzip.decompress(call['data']))
    assert reparsed == request


def test_exporter_fails_soft_on_rejection():
    request = build_export_request(parse_collapsed(FIXTURE.read_text()), profile_id=PROFILE_ID)
    exporter = ProfilesExporter(
        _FakeSession(_FakeResponse(503, 'overloaded')), 'https://logfire.example/v1development/profiles'
    )
    with pytest.warns(UserWarning, match='profile export rejected'):
        assert exporter.export(request) is False


def test_exporter_fails_soft_on_exception():
    request = build_export_request(parse_collapsed(FIXTURE.read_text()), profile_id=PROFILE_ID)
    exporter = ProfilesExporter(_FakeSession(ConnectionError('boom')), 'https://logfire.example/v1development/profiles')
    with pytest.warns(UserWarning, match='failed to export profile'):
        assert exporter.export(request) is False
