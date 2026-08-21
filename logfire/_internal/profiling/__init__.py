"""Experimental: ship Python sampling-profiler data to the OpenTelemetry profiles signal.

This package converts the output of the Python 3.15 `profiling.sampling`
profiler (Tachyon) into OTLP profiles and exports them over HTTP:

- `collapsed` parses the profiler's folded-stack output
- `otlp` converts it to an OTLP profiles export request
- `exporter` posts that request
- `supervisor` runs the profiler subprocess in a loop and ties the three together

Still to come: per-span correlation (pointing each sample at the span it was
taken in).
"""
