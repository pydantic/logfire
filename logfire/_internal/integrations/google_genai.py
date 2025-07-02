from __future__ import annotations

import json
from typing import Any

from opentelemetry._events import Event, EventLogger, EventLoggerProvider
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.trace import get_current_span

import logfire
from logfire._internal.utils import handle_internal_errors


class SpanEventLogger(EventLogger):
    @handle_internal_errors
    def emit(self, event: Event) -> None:
        span = get_current_span()
        assert isinstance(event.body, dict)
        body: dict[str, Any] = {**event.body}
        if event.name == 'gen_ai.choice':
            parts = body.pop('content')['parts']
            new_parts: list[dict[str, Any] | str] = []
            for part in parts:
                new_part: str | dict[str, Any] = {k: v for k, v in part.items() if v is not None}
                if list(new_part.keys()) == ['text']:  # pragma: no branch
                    new_part = new_part['text']
                new_parts.append(new_part)
            body['message'] = {'role': 'assistant', 'content': new_parts}
        else:
            body['role'] = body.get('role', event.name.split('.')[1])

        span.add_event(event.name, attributes={'event_body': json.dumps(body)})


class SpanEventLoggerProvider(EventLoggerProvider):
    def get_event_logger(self, *args: Any, **kwargs: Any) -> SpanEventLogger:
        return SpanEventLogger(*args, **kwargs)


def instrument_google_genai(logfire_instance: logfire.Logfire):
    GoogleGenAiSdkInstrumentor().instrument(
        event_logger_provider=SpanEventLoggerProvider(),
        tracer_provider=logfire_instance.config.get_tracer_provider(),
        meter_provider=logfire_instance.config.get_meter_provider(),
    )
