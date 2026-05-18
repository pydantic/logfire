# Vendored OTLP profiles protobuf bindings

`profiles_pb2.py` / `profiles_service_pb2.py` (and their `.pyi` stubs) are
**generated** code, vendored here rather than imported from the
`opentelemetry-proto` PyPI package.

## Why vendored

The OpenTelemetry profiles signal is alpha (`v1development`). The
`opentelemetry-proto` PyPI package (≤ 1.41.x) is generated from the
`opentelemetry-proto` repo pinned at `v1.9.0`, which carries an **outdated**
`Sample` message: its field numbers (`values`, `attribute_indices`,
`link_index`) were renumbered in proto `v1.10.0`. A `Sample` serialized with
the stale numbering is silently misread by current consumers (e.g. Grafana
Pyroscope), so we cannot use the PyPI bindings.

These files are generated from `opentelemetry-proto` **v1.10.0** instead.

## When this directory can be deleted

Once the `opentelemetry-proto` PyPI package ships bindings generated from
proto ≥ `v1.10.0`, delete this directory and import from
`opentelemetry.proto.profiles...` directly. The upstream pin bump is tracked
in <https://github.com/open-telemetry/opentelemetry-python/pull/5223>.

## Regeneration

The proto `package` / file paths are renamed to `lf_otlp.*` so the descriptors
do not collide with the (stale) copy registered by the installed
`opentelemetry-proto` package — protobuf's descriptor pool rejects two files
with the same name. This rename is purely about the descriptor registry; it
does not affect the wire format (only field numbers do).

To regenerate, fetch `profiles.proto` and `profiles_service.proto` from
`opentelemetry-proto` at the desired tag, place them under an `lf_otlp/`
directory with `opentelemetry.proto.{profiles.v1development,collector.profiles.v1development}`
rewritten to `lf_otlp.{profiles,collector}`, then:

```sh
uvx --from grpcio-tools --with mypy-protobuf python -m grpc_tools.protoc \
  --proto_path=<root> --python_out=<out> --mypy_out=<out> \
  lf_otlp/profiles.proto lf_otlp/profiles_service.proto
```

Finally rewrite `from lf_otlp import profiles_pb2` to
`from logfire._internal.profiling._proto import profiles_pb2` in the generated
`profiles_service_pb2.{py,pyi}`. `common`/`resource` come from the installed
`opentelemetry-proto` package (those signals are stable).
