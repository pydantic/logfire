"""Vendored OTLP profiles protobuf bindings.

Generated from the canonical `open-telemetry/opentelemetry-proto` repo (tag
`v1.10.0`, the `v1development` profiles signal). Vendored because the
`opentelemetry-proto` PyPI package ships an outdated snapshot of this
still-alpha proto: its `Sample` field numbers predate a renumbering and are
wire-incompatible with current consumers (e.g. Grafana Pyroscope).

See `README.md` in this directory for the regeneration recipe and the
condition under which this directory can be deleted.
"""
