from logfire import LevelName as LevelName, Logfire as Logfire
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from logfire.propagate import attach_context as attach_context, get_context as get_context

def instrument_mcp(logfire_instance: Logfire, propagate_otel_context: bool): ...
