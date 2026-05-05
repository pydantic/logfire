"""Build the `X-Logfire-Telemetry` request header.

The header carries non-sensitive information about the SDK and how it is
configured, encoded as a compact JSON object. The backend uses it to answer
questions like which SDK versions are still in active use, which Python
versions we can drop, and which configuration options users actually enable.
Secrets (`token`, `api_key`, `service_name`, etc.) are never included.
"""

from __future__ import annotations

import functools
import json
import sys
from typing import TYPE_CHECKING, Any

from logfire.version import VERSION

if TYPE_CHECKING:
    from .config import LogfireConfig


TELEMETRY_HEADER_NAME = 'X-Logfire-Telemetry'


@functools.cache
def _base_telemetry_pairs() -> dict[str, Any]:
    # Each field below has an explicit rationale; do not add a field unless you have one.
    return {
        # SDK version: the primary signal for deprecation planning — which versions
        # are still in active use so we know when it is safe to drop one.
        'sdk_version': VERSION,
        # SDK language: lets the same backend ingestion logic distinguish python
        # from future SDKs (JS, Rust) without having to parse User-Agent.
        'sdk_language': 'python',
        # Python version: tells us when we can drop support for an older Python.
        'python_version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
        # Implementation: spotting non-CPython users (pypy, graalpy) before
        # changing anything that depends on CPython-specific behaviour.
        'implementation': sys.implementation.name,
        # OS: same idea — confirm Windows / Linux / macOS coverage before
        # touching platform-sensitive code paths.
        'os': sys.platform,
    }


def _config_telemetry_pairs(config: LogfireConfig) -> dict[str, Any]:
    """Pick fields of `LogfireConfig` that are useful for product analytics.

    Each field below has an explicit rationale; do not add a field unless you have
    one. Everything else either duplicates information the server already knows,
    isn't actionable, or risks leaking sensitive data (token, api_key,
    service_name, environment, etc.).
    """
    # Multi-project usage: how many users configure more than one write token in
    # a single SDK instance. Drives auth/routing roadmap decisions.
    token = config.token
    if isinstance(token, list):
        token_count = len(token)
    elif token:
        token_count = 1
    else:
        token_count = 0

    pairs: dict[str, Any] = {
        # Adoption signal for the `code_source=` option (newer feature): tells us
        # whether the integration with the source-code link UI is worth investing in.
        'code_source_set': config.code_source is not None,
        # Adoption signal for the variables / feature-flag feature (newer feature):
        # informs whether to keep building on it.
        'variables_set': config.variables is not None,
        'token_count': token_count,
    }

    if config._service_instance_id:  # pyright: ignore[reportPrivateUsage]
        # Mirrors the OTLP resource attribute of the same name
        # (https://opentelemetry.io/docs/specs/semconv/registry/attributes/service/#service-instance-id).
        # Carrying it on the header lets the backend correlate metadata with the spans
        # this SDK instance is exporting, even on requests that don't carry an OTLP body
        # (token validation, variables fetch, CRUD endpoints).
        pairs['service_instance_id'] = config._service_instance_id  # pyright: ignore[reportPrivateUsage]

    return pairs


def build_telemetry_header(config: LogfireConfig | None = None) -> str:
    """Return the JSON-encoded value for the `X-Logfire-Telemetry` header."""
    pairs: dict[str, Any] = {**_base_telemetry_pairs()}
    if config is not None:
        pairs.update(_config_telemetry_pairs(config))
    return json.dumps(pairs, separators=(',', ':'))
