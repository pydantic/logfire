from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

try:
    import logfire

    logfire_installed = True
except ImportError:
    logfire_installed = False


if TYPE_CHECKING:

    class LogfireConfig: ...

    GLOBAL_CONFIG = LogfireConfig()

    class Logfire:
        def __init__(
            self,
            *,
            config: LogfireConfig = GLOBAL_CONFIG,
            sample_rate: float | None = None,
            tags: Sequence[str] = (),
            console_log: bool = True,
            otel_scope: str = 'logfire',
        ) -> None: ...

else:

    class Logfire:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if logfire_installed:
                return logfire.Logfire(*args, **kwargs)
