from __future__ import annotations

import base64
import json
from typing import Any

from opentelemetry._events import Event, EventLogger, EventLoggerProvider
from opentelemetry.trace import get_current_span
from typing_extensions import TypeAlias

import logfire
from logfire._internal.utils import handle_internal_errors, safe_repr

try:
    from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
except ImportError:
    raise RuntimeError(
        'The `logfire.instrument_google_genai()` method '
        'requires the `opentelemetry-instrumentation-google-genai` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[google-genai]'"
    )

try:
    from opentelemetry.instrumentation.google_genai import dict_util

    original_flatten_compound_value = dict_util._flatten_compound_value  # type: ignore

    def wrapped_flatten_compound_value(key: str, value: Any, *args: Any, **kwargs: Any):
        try:
            return original_flatten_compound_value(key, value, *args, **kwargs)
        except Exception:
            return {key: safe_repr(value)}

    dict_util._flatten_compound_value = wrapped_flatten_compound_value  # type: ignore
except Exception:  # pragma: no cover
    pass

Part: TypeAlias = 'dict[str, Any] | str'


def default_json(x: Any) -> str:
    return base64.b64encode(x).decode('utf-8') if isinstance(x, bytes) else x


class SpanEventLogger(EventLogger):
    @handle_internal_errors
    def emit(self, event: Event) -> None:
        span = get_current_span()
        assert isinstance(event.body, dict)
        body: dict[str, Any] = {**event.body}
        if event.name == 'gen_ai.choice':
            if 'content' in body and isinstance(body['content'], dict):
                parts = body.pop('content')['parts']
                new_parts = [transform_part(part) for part in parts]
                body['message'] = {'role': 'assistant', 'content': new_parts}
        else:
            if 'content' in body:  # pragma: no branch
                body['content'] = transform_part(body['content'])
            body['role'] = body.get('role', event.name.split('.')[1])

        span.add_event(event.name, attributes={'event_body': json.dumps(body, default=default_json)})


def transform_part(part: Part) -> Part:
    if isinstance(part, str):
        return part
    new_part = {k: v for k, v in part.items() if v is not None}
    if list(new_part.keys()) == ['text']:
        return new_part['text']
    return new_part


class SpanEventLoggerProvider(EventLoggerProvider):
    def get_event_logger(self, *args: Any, **kwargs: Any) -> SpanEventLogger:
        return SpanEventLogger(*args, **kwargs)


def instrument_google_genai(logfire_instance: logfire.Logfire, **kwargs: Any):
    GoogleGenAiSdkInstrumentor().instrument(
        **{
            'event_logger_provider': SpanEventLoggerProvider(),
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        }
    )
