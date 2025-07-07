from __future__ import annotations

import base64
import json
from typing import Any

from opentelemetry._events import Event, EventLogger, EventLoggerProvider
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.trace import get_current_span
from typing_extensions import TypeAlias

import logfire
from logfire._internal.utils import handle_internal_errors

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
            if 'content' in body:  # pragma: no branch
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


def instrument_google_genai(logfire_instance: logfire.Logfire):
    GoogleGenAiSdkInstrumentor().instrument(
        event_logger_provider=SpanEventLoggerProvider(),
        tracer_provider=logfire_instance.config.get_tracer_provider(),
        meter_provider=logfire_instance.config.get_meter_provider(),
    )
