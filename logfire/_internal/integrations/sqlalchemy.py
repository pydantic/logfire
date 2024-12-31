from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

try:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from logfire.integrations.sqlalchemy import CommenterOptions
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_sqlalchemy()` requires the `opentelemetry-instrumentation-sqlalchemy` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[sqlalchemy]'"
    )

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine


def instrument_sqlalchemy(
    engine: AsyncEngine | Engine | None,
    enable_commenter: bool,
    commenter_options: CommenterOptions,
    **kwargs: Any,
) -> None:
    """Instrument the `sqlalchemy` module so that spans are automatically created for each query.

    See the `Logfire.instrument_sqlalchemy` method for details.
    """
    with contextlib.suppress(ImportError):
        from sqlalchemy.ext.asyncio import AsyncEngine

        if isinstance(engine, AsyncEngine):
            engine = engine.sync_engine
    return SQLAlchemyInstrumentor().instrument(engine=engine, **kwargs)
