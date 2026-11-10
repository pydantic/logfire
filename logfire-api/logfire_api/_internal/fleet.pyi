import dataclasses
from .stack_info import warn_at_user_stacklevel as warn_at_user_stacklevel
from .utils import platform_is_emscripten as platform_is_emscripten
from collections.abc import Mapping
from datetime import timedelta
from logfire_fleet_otel import LogfireFleet
from pathlib import Path

FLEET_CONTRACT: int

@dataclasses.dataclass
class FleetOptions:
    """Options for joining Logfire Fleet.

    Each one left as `None` comes from its environment variable, which is what the Fleet setup page
    in Logfire gives you.
    """
    endpoint: str | None = ...
    headers: Mapping[str, str] | None = ...
    state_dir: str | Path | None = ...
    heartbeat_interval: float | timedelta | None = ...

class LogfireFleetWarning(UserWarning):
    """The SDK couldn't join Logfire Fleet, so it runs unmanaged."""

def load_fleet(options: FleetOptions) -> LogfireFleet | None:
    """The Fleet client's hook for `options`, or `None` (with a warning) where it can't run.

    It never raises: telemetry is sent either way, under the SDK's own settings.
    """
