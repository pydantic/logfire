from sqlalchemy import Engine
from typing_extensions import TypedDict, Unpack

class CommenterOptions(TypedDict, total=False):
    db_driver: bool
    db_framework: bool
    opentelemetry_values: bool

class SQLAlchemyInstrumentKwargs(TypedDict, total=False):
    engine: Engine | None
    enable_commenter: bool | None
    commenter_options: CommenterOptions | None
    skip_dep_check: bool

def instrument_sqlalchemy(**kwargs: Unpack[SQLAlchemyInstrumentKwargs]) -> None:
    """Instrument the `sqlalchemy` module so that spans are automatically created for each query.

    See the `Logfire.instrument_sqlalchemy` method for details.
    """
