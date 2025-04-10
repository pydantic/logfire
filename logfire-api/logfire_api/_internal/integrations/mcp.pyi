from logfire import LevelName as LevelName, Logfire as Logfire
from logfire._internal.utils import handle_internal_errors as handle_internal_errors

def instrument_mcp(logfire_instance: Logfire): ...
