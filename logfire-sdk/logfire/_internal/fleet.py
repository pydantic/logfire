"""`logfire.configure(fleet=...)`: the SDK under a Logfire Fleet policy.

The Fleet client lives in the `logfire-fleet-otel` package (the `fleet` extra). This module only
finds it and checks it speaks the same contract; `config.py` calls it at the points where the
policy has to act as the SDK is built (see `logfire_fleet_otel.LogfireFleet`).
"""

from __future__ import annotations

import dataclasses
import importlib
import os
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from .stack_info import warn_at_user_stacklevel
from .utils import platform_is_emscripten

# The contract version of `logfire_fleet_otel.LogfireFleet` this SDK calls.
FLEET_CONTRACT = 1


@dataclasses.dataclass
class FleetOptions:
    """Options for joining Logfire Fleet.

    Each one left as `None` comes from its environment variable, which is what the Fleet setup page
    in Logfire gives you.
    """

    endpoint: str | None = None
    """The Fleet server's OpAMP endpoint. Defaults to the `OTEL_OPAMP_ENDPOINT` environment variable."""

    headers: Mapping[str, str] | None = None
    """Headers sent to the Fleet server, such as the enrollment key's `Authorization` header.
    Defaults to the `OTEL_OPAMP_HEADERS` environment variable."""

    state_dir: str | Path | None = None
    """Where the last policy received and the instance ID are kept, so a restart starts with them
    even when the Fleet server can't be reached. Defaults to the `OTEL_OPAMP_STATE_DIR` environment
    variable, else a directory of the Fleet client's own; `'none'` keeps nothing."""

    heartbeat_interval: float | timedelta | None = None
    """How often to tell the Fleet server this instance is alive, in seconds. Defaults to the
    `OTEL_OPAMP_HEARTBEAT_INTERVAL` environment variable, else the client's default."""


class LogfireFleetWarning(UserWarning):
    """The SDK couldn't join Logfire Fleet, so it runs unmanaged."""


def load_fleet(options: FleetOptions) -> Any:
    """The Fleet client's hook for `options`, or `None` (with a warning) where it can't run.

    It never raises: telemetry is sent either way, under the SDK's own settings.
    """
    if platform_is_emscripten():  # pragma: no cover
        _warn('Logfire Fleet needs threads, which this platform does not have')
        return None
    try:
        # Not typed for this SDK: the contract is checked below instead.
        logfire_fleet_otel: Any = importlib.import_module('logfire_fleet_otel')
    except ImportError:
        _warn("Logfire Fleet needs the `fleet` extra: `pip install 'logfire[fleet]'`")
        return None
    contract = getattr(logfire_fleet_otel, 'LOGFIRE_FLEET_CONTRACT', None)
    if contract != FLEET_CONTRACT:
        _warn(
            f'the installed logfire-fleet-otel speaks contract {contract}, not {FLEET_CONTRACT}: '
            "install a matching version with `pip install -U 'logfire[fleet]'`"
        )
        return None
    if not (options.endpoint or os.environ.get('OTEL_OPAMP_ENDPOINT')) and not _disabled():
        _warn('no Fleet endpoint is set: set `OTEL_OPAMP_ENDPOINT` or `FleetOptions(endpoint=...)`')
        return None
    try:
        return logfire_fleet_otel.logfire_fleet(
            endpoint=options.endpoint,
            headers=options.headers,
            state_dir=options.state_dir,
            heartbeat_interval=options.heartbeat_interval,
        )
    except Exception as e:  # pragma: no cover - the client promises not to raise
        _warn(f'the Fleet client could not start: {e!r}')
        return None


def _disabled() -> bool:
    return os.environ.get('OTEL_OPAMP_DISABLED', '').strip().lower() in ('1', 'true', 'yes')


def _warn(reason: str) -> None:
    warn_at_user_stacklevel(f'{reason}. The SDK runs unmanaged.', category=LogfireFleetWarning)
