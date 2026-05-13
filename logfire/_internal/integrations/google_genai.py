from __future__ import annotations

import base64
import json
from typing import Any

from opentelemetry._logs import Logger, LoggerProvider, LogRecord
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

    original_flatten_compound_value = dict_util._flatten_compound_value  # pyright: ignore[reportPrivateUsage]

    def wrapped_flatten_compound_value(key: str, value: Any, *args: Any, **kwargs: Any):
        try:
            return original_flatten_compound_value(key, value, *args, **kwargs)
        except Exception:  # pragma: no cover
            return {key: safe_repr(value)}

    dict_util._flatten_compound_value = wrapped_flatten_compound_value  # pyright: ignore[reportPrivateUsage]
except Exception:  # pragma: no cover
    pass


try:
    from opentelemetry.instrumentation.google_genai import generate_content
    from pydantic import TypeAdapter

    original_to_dict: Any = generate_content._to_dict  # pyright: ignore[reportPrivateUsage]

    ANY_ADAPTER = TypeAdapter[Any](Any)

    def wrapped_to_dict(obj: object) -> object:
        try:
            return original_to_dict(obj)
        except Exception:  # pragma: no cover
            try:
                return ANY_ADAPTER.dump_python(obj, mode='json')
            except Exception:  # pragma: no cover
                return safe_repr(obj)

    generate_content._to_dict = wrapped_to_dict  # pyright: ignore[reportPrivateUsage]

except Exception:  # pragma: no cover
    pass


Part: TypeAlias = 'dict[str, Any] | str'


def default_json(x: Any) -> str:
    return base64.b64encode(x).decode('utf-8') if isinstance(x, bytes) else x


def _strip_cycles(obj: Any, _seen: set[int] | None = None) -> Any:
    """Return a copy of ``obj`` with any container cycles replaced by ``safe_repr``.

    ``json.dumps`` raises ``ValueError: Circular reference detected`` when a dict/list
    contains itself anywhere in its descendants. This can happen when upstream
    instrumentation captures Gemini SDK objects (e.g. an uploaded ``File``) whose
    ``_to_dict`` representation contains self-references. See pydantic/logfire#1881.
    """
    if _seen is None:
        _seen = set()
    if isinstance(obj, dict):
        obj_id = id(obj)
        if obj_id in _seen:
            return safe_repr(obj)
        _seen.add(obj_id)
        try:
            return {k: _strip_cycles(v, _seen) for k, v in obj.items()}
        finally:
            _seen.discard(obj_id)
    if isinstance(obj, (list, tuple)):
        obj_id = id(obj)
        if obj_id in _seen:
            return safe_repr(obj)
        _seen.add(obj_id)
        try:
            return [_strip_cycles(v, _seen) for v in obj]
        finally:
            _seen.discard(obj_id)
    return obj


class SpanEventLogger(Logger):
    @handle_internal_errors
    def emit(self, record: LogRecord) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        span = get_current_span()
        assert isinstance(record.body, dict)
        assert record.event_name
        body: dict[str, Any] = {**record.body}
        if record.event_name == 'gen_ai.choice':
            if 'content' in body and isinstance(body['content'], dict):
                parts = body.pop('content')['parts']
                new_parts = [transform_part(part) for part in parts] if parts else []
                body['message'] = {'role': 'assistant', 'content': new_parts}
        else:
            if 'content' in body:  # pragma: no branch
                if isinstance(body['content'], (list, tuple, set)):
                    body['content'] = [transform_part(part) for part in body['content']]  # type: ignore  # pragma: no cover
                else:
                    body['content'] = transform_part(body['content'])
            body['role'] = body.get('role', record.event_name.split('.')[1])

        try:
            event_body = json.dumps(body, default=default_json)
        except ValueError:
            # Fall back to a cycle-stripped copy so a single bad payload (e.g. a
            # Gemini File reference with a self-loop) cannot drop the span event.
            event_body = json.dumps(_strip_cycles(body), default=default_json)
        span.add_event(record.event_name, attributes={'event_body': event_body})


def transform_part(part: Part) -> Part:
    if isinstance(part, str):
        return part
    new_part = {k: v for k, v in part.items() if v is not None}
    if list(new_part.keys()) == ['text']:
        return new_part['text']
    return new_part


class SpanEventLoggerProvider(LoggerProvider):
    def get_logger(self, *args: Any, **kwargs: Any) -> SpanEventLogger:
        return SpanEventLogger(*args, **kwargs)


def instrument_google_genai(logfire_instance: logfire.Logfire, **kwargs: Any):
    GoogleGenAiSdkInstrumentor().instrument(
        **{
            'logger_provider': SpanEventLoggerProvider(),
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        }
    )
