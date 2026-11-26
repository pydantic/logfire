import logfire
from _typeshed import Incomplete
from logfire._internal.integrations.llm_providers.usage import gateway_header_cost as gateway_header_cost, gateway_reported_cost as gateway_reported_cost
from logfire._internal.utils import handle_internal_errors as handle_internal_errors, safe_repr as safe_repr
from typing import Any

CAPTURE_MESSAGE_CONTENT_ENV_VAR: str
LEGACY_CAPTURE_MESSAGE_CONTENT_VALUES: Incomplete
EMIT_EVENT_ENV_VAR: str
original_flatten_compound_value: Incomplete

def wrapped_flatten_compound_value(key: str, value: Any, *args: Any, **kwargs: Any): ...

original_apply_response_attributes: Incomplete

def wrapped_apply_response_attributes(response: Any, finish_reasons: Any, invocation: Any, *args: Any, **kwargs: Any): ...
def instrument_google_genai(logfire_instance: logfire.Logfire, **kwargs: Any): ...
