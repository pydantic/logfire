from logfire import Logfire as Logfire
from logfire._internal.stack_info import warn_at_user_stacklevel as warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from snowflake.connector.connection import SnowflakeConnection
from types import ModuleType

def instrument_snowflake(logfire_instance: Logfire, conn_or_module: ModuleType | SnowflakeConnection | None, capture_parameters: bool) -> None: ...
