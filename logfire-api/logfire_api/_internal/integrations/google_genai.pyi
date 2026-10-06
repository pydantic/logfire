import logfire
from _typeshed import Incomplete
from logfire._internal.utils import safe_repr as safe_repr
from typing import Any

CAPTURE_MESSAGE_CONTENT_ENV_VAR: str
LEGACY_CAPTURE_MESSAGE_CONTENT_VALUES: Incomplete
EMIT_EVENT_ENV_VAR: str
original_flatten_compound_value: Incomplete

def wrapped_flatten_compound_value(key: str, value: Any, *args: Any, **kwargs: Any): ...
def instrument_google_genai(logfire_instance: logfire.Logfire, **kwargs: Any): ...
