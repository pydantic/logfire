"""Experimental: ship Python sampling-profiler data to the OpenTelemetry profiles signal.

This package converts the output of the Python 3.15 `profiling.sampling`
profiler (Tachyon) into OTLP profiles and exports them over HTTP.

Status: work in progress. Implemented here are the conversion (`collapsed` +
`otlp`) and the HTTP `exporter`. Still to come: the supervisor that actually
runs the profiler subprocess, wiring into `logfire.configure()`, and per-span
correlation.
"""
