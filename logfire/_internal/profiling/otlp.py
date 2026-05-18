"""Build an OTLP profiles export request from Tachyon folded stacks.

This uses the protobuf bindings shipped by `opentelemetry-proto` directly
(`opentelemetry.proto.profiles.v1development`) - there is no hand-written
profile model. The current OTLP profiles model keeps a single request-level
`ProfilesDictionary` holding the shared string/function/location/stack/
attribute tables; every `Sample` references into it by index.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

# common/resource are stable signals - the installed opentelemetry-proto is fine.
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope
from opentelemetry.proto.resource.v1.resource_pb2 import Resource

# profiles is an alpha signal; use the vendored (current) bindings, not the
# outdated snapshot in the opentelemetry-proto PyPI package. See _proto/.
from ._proto import profiles_pb2 as pb
from ._proto.profiles_service_pb2 import ExportProfilesServiceRequest
from .collapsed import FoldedStack


class _DictionaryBuilder:
    """Interns entries into a shared `ProfilesDictionary`, returning each entry's index."""

    def __init__(self) -> None:
        self.dictionary = pb.ProfilesDictionary()
        self.dictionary.string_table.append('')  # index 0 is "" by convention
        self._strings: dict[str, int] = {'': 0}
        self._functions: dict[tuple[int, int], int] = {}
        self._locations: dict[tuple[int, int], int] = {}
        self._stacks: dict[tuple[int, ...], int] = {}
        self._attributes: dict[tuple[str, int], int] = {}
        # OTLP profiles require every Location to reference a Mapping. A pure
        # Python profile has no native mappings, so use a single synthetic
        # entry at index 0 - consumers (pprof, Pyroscope) reject a Location
        # whose mapping_index points outside the mapping table.
        self.dictionary.mapping_table.append(pb.Mapping(filename_strindex=self.string('python')))

    def string(self, value: str) -> int:
        idx = self._strings.get(value)
        if idx is None:
            idx = len(self.dictionary.string_table)
            self.dictionary.string_table.append(value)
            self._strings[value] = idx
        return idx

    def function(self, filename: str, name: str) -> int:
        key = (self.string(filename), self.string(name))
        idx = self._functions.get(key)
        if idx is None:
            idx = len(self.dictionary.function_table)
            self.dictionary.function_table.append(pb.Function(filename_strindex=key[0], name_strindex=key[1]))
            self._functions[key] = idx
        return idx

    def location(self, filename: str, name: str, line: int) -> int:
        function_index = self.function(filename, name)
        key = (function_index, line)
        idx = self._locations.get(key)
        if idx is None:
            idx = len(self.dictionary.location_table)
            self.dictionary.location_table.append(
                pb.Location(
                    mapping_index=0,
                    lines=[pb.Line(function_index=function_index, line=line)],
                )
            )
            self._locations[key] = idx
        return idx

    def stack(self, location_indices: tuple[int, ...]) -> int:
        idx = self._stacks.get(location_indices)
        if idx is None:
            idx = len(self.dictionary.stack_table)
            self.dictionary.stack_table.append(pb.Stack(location_indices=location_indices))
            self._stacks[location_indices] = idx
        return idx

    def int_attribute(self, key: str, value: int) -> int:
        cache_key = (key, value)
        idx = self._attributes.get(cache_key)
        if idx is None:
            idx = len(self.dictionary.attribute_table)
            self.dictionary.attribute_table.append(
                pb.KeyValueAndUnit(
                    key_strindex=self.string(key),
                    value=AnyValue(int_value=value),
                )
            )
            self._attributes[cache_key] = idx
        return idx


def build_export_request(
    stacks: Iterable[FoldedStack],
    *,
    resource: Resource | None = None,
    scope_name: str = 'logfire.profiling',
    scope_version: str = '',
    sample_type: str = 'samples',
    sample_unit: str = 'count',
    period_type: str = '',
    period_unit: str = '',
    period: int = 0,
    start_time_unix_nano: int = 0,
    duration_nano: int = 0,
    profile_id: bytes | None = None,
) -> ExportProfilesServiceRequest:
    """Convert folded stacks into a ready-to-POST `ExportProfilesServiceRequest`.

    `period`/`period_type` describe the sampling interval (e.g. type `cpu`,
    unit `nanoseconds`, period 500000 for a 2 kHz profiler) - the collapsed
    format does not carry it, so the caller supplies it from the `-r` rate.
    """
    builder = _DictionaryBuilder()
    profile = pb.Profile(
        sample_type=pb.ValueType(
            type_strindex=builder.string(sample_type),
            unit_strindex=builder.string(sample_unit),
        ),
        period_type=pb.ValueType(
            type_strindex=builder.string(period_type),
            unit_strindex=builder.string(period_unit),
        ),
        period=period,
        time_unix_nano=start_time_unix_nano,
        duration_nano=duration_nano,
        profile_id=profile_id if profile_id is not None else os.urandom(16),
    )

    for stack in stacks:
        location_indices = tuple(
            builder.location(frame.filename, frame.function, frame.lineno) for frame in stack.frames
        )
        sample = pb.Sample(
            stack_index=builder.stack(location_indices),
            values=[stack.count],
        )
        if stack.thread_id:
            # `thread.id` is an OTel semantic-convention attribute. A later
            # step will add `link_index` pointing at a Link(trace_id, span_id).
            sample.attribute_indices.append(builder.int_attribute('thread.id', stack.thread_id))
        profile.samples.append(sample)

    return ExportProfilesServiceRequest(
        dictionary=builder.dictionary,
        resource_profiles=[
            pb.ResourceProfiles(
                resource=resource or Resource(),
                scope_profiles=[
                    pb.ScopeProfiles(
                        scope=InstrumentationScope(name=scope_name, version=scope_version),
                        profiles=[profile],
                    )
                ],
            )
        ],
    )
