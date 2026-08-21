"""Build an OTLP profiles export request from Tachyon folded stacks.

This uses the protobuf bindings shipped by `opentelemetry-proto` directly
(`opentelemetry.proto.profiles.v1development`) - there is no hand-written
profile model. The OTLP profiles model keeps a single request-level
`ProfilesDictionary` holding the shared string/function/location/stack/
attribute tables; every `Sample` references into it by index.

The profiles signal is still in development, and its schema changed
incompatibly (fields were renumbered) in `opentelemetry-proto` v1.10.0, which
reached PyPI in `opentelemetry-proto` 1.43.0. Older bindings serialize a
`Sample` that current consumers silently misread, so `profiles_proto_is_current`
lets callers refuse to export rather than send garbage.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence

from opentelemetry.proto.collector.profiles.v1development.profiles_service_pb2 import (
    ExportProfilesServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, InstrumentationScope, KeyValue
from opentelemetry.proto.profiles.v1development import profiles_pb2 as pb
from opentelemetry.proto.resource.v1.resource_pb2 import Resource

from .collapsed import FoldedStack

# The first `opentelemetry-proto` release generated from proto v1.10.0, i.e. the
# oldest one whose profiles bindings match what this module builds.
MIN_PROTO_VERSION = '1.43.0'


def profiles_proto_is_current() -> bool:
    """Whether the installed `opentelemetry-proto` profiles bindings are the ones we build against.

    Detected from the wire format rather than the package version: `Sample.values`
    is field 4 from proto v1.10.0 onwards and field 2 before it.
    """
    try:
        return pb.Sample.DESCRIPTOR.fields_by_name['values'].number == 4
    except KeyError:  # pragma: no cover
        # A schema old or new enough not to have the field at all.
        return False


class _DictionaryBuilder:
    """Interns entries into a shared `ProfilesDictionary`, returning each entry's index."""

    def __init__(self) -> None:
        # Every table in a ProfilesDictionary must start with a zero value, so that an index of 0
        # into it means 'not set'. Real entries therefore start at index 1.
        self.dictionary = pb.ProfilesDictionary(
            mapping_table=[pb.Mapping()],
            location_table=[pb.Location()],
            function_table=[pb.Function()],
            link_table=[pb.Link()],
            string_table=[''],
            attribute_table=[pb.KeyValueAndUnit()],
            stack_table=[pb.Stack()],
        )
        self._strings: dict[str, int] = {'': 0}
        self._functions: dict[tuple[int, int], int] = {}
        self._locations: dict[tuple[int, int], int] = {}
        self._stacks: dict[tuple[int, ...], int] = {}
        self._attributes: dict[tuple[str, int], int] = {}

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
                    # 0 is the null mapping: a pure Python frame isn't in any binary mapping.
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


def resource_from_attributes(attributes: Mapping[str, object]) -> Resource:
    """Build an OTLP `Resource` from a flat attribute mapping."""
    return Resource(attributes=[KeyValue(key=str(key), value=_any_value(value)) for key, value in attributes.items()])


def _any_value(value: object) -> AnyValue:
    # bool first: it's a subclass of int.
    if isinstance(value, bool):
        return AnyValue(bool_value=value)
    if isinstance(value, int):
        return AnyValue(int_value=value)
    if isinstance(value, float):
        return AnyValue(double_value=value)
    if isinstance(value, str):
        return AnyValue(string_value=value)
    if isinstance(value, Sequence):
        return AnyValue(array_value=ArrayValue(values=[_any_value(item) for item in value]))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return AnyValue(string_value=str(value))
