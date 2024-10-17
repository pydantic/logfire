from logfire import Logfire as Logfire
from typing_extensions import TypedDict, Unpack

class AsyncPGInstrumentKwargs(TypedDict, total=False):
    skip_dep_check: bool

def instrument_asyncpg(logfire_instance: Logfire, **kwargs: Unpack[AsyncPGInstrumentKwargs]) -> None:
    """Instrument the `asyncpg` module so that spans are automatically created for each query.

    See the `Logfire.instrument_asyncpg` method for details.
    """
