"""Build the `X-Logfire-Telemetry` request header.

The header carries non-sensitive, config-derived signals about how this SDK
instance is configured, encoded as a compact JSON object. SDK/runtime identity
(version, language, Python version, OS, etc.) lives on the standard
`User-Agent` header instead — see `UA_HEADER` in `_internal/client.py`.
Secrets (`token`, `api_key`, `service_name`, etc.) are never included.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import LogfireConfig


TELEMETRY_HEADER_NAME = 'X-Logfire-Telemetry'


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
        # High-cardinality per-process identifier — kept here rather than in
        # User-Agent because user-agent strings are typically aggregated and a
        # per-instance id would explode the cardinality of any UA-based analytics.
        pairs['service_instance_id'] = config._service_instance_id  # pyright: ignore[reportPrivateUsage]

    return pairs


def build_telemetry_header(config: LogfireConfig | None = None) -> str | None:
    """Return the JSON-encoded `X-Logfire-Telemetry` value, or None if no config.

    Without a `LogfireConfig` there is nothing config-specific to report — the
    SDK/runtime identity is already in `User-Agent`, so callers should simply
    omit the header in that case.
    """
    if config is None:
        return None
    return json.dumps(_config_telemetry_pairs(config), separators=(',', ':'))
