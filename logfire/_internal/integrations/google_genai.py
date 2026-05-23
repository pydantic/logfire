from __future__ import annotations

import base64
import json
from typing import Any, TypeAlias

from opentelemetry._logs import Logger, LoggerProvider, LogRecord
from opentelemetry.trace import get_current_span

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


try:
    from opentelemetry.instrumentation.google_genai import generate_content as _gc_module

    _Helper = _gc_module._GenerateContentInstrumentationHelper  # pyright: ignore[reportPrivateUsage]
    _original_maybe_update = _Helper._maybe_update_token_counts  # pyright: ignore[reportPrivateUsage]
    _original_create_final = _Helper.create_final_attributes

    def _wrapped_maybe_update_token_counts(self: Any, response: Any) -> None:
        _original_maybe_update(self, response)
        try:
            metadata = getattr(response, 'usage_metadata', None)
            if metadata is None:
                return
            # "keep last non-zero" — streaming sends partial chunks; cached/thoughts/tool_use
            # counts typically only appear in the final chunk.
            if cached := getattr(metadata, 'cached_content_token_count', None):
                self._lf_cache_read = cached
            if thoughts := getattr(metadata, 'thoughts_token_count', None):
                self._lf_thoughts = thoughts
            if tool_use := getattr(metadata, 'tool_use_prompt_token_count', None):
                self._lf_tool_use_prompt = tool_use
            self._lf_response = response
        except Exception:  # pragma: no cover
            pass

    def _wrapped_create_final_attributes(self: Any) -> dict[str, Any]:
        attrs = _original_create_final(self)
        try:
            if cached := getattr(self, '_lf_cache_read', None):
                attrs['gen_ai.usage.cache_read.input_tokens'] = cached
            if thoughts := getattr(self, '_lf_thoughts', None):
                attrs['gen_ai.usage.details.thoughts_tokens'] = thoughts
            if tool_use := getattr(self, '_lf_tool_use_prompt', None):
                attrs['gen_ai.usage.details.tool_use_prompt_tokens'] = tool_use
            response = getattr(self, '_lf_response', None)
            if response is not None:
                try:
                    from genai_prices import calc_price, extract_usage

                    # genai_prices expects the camelCase JSON keys ('usageMetadata', 'modelVersion');
                    # google-genai pydantic models use snake_case fields with camelCase aliases.
                    usage_data = extract_usage(response.model_dump(by_alias=True), provider_id='google')
                    if usage_data.model is not None:
                        attrs['operation.cost'] = float(
                            calc_price(
                                usage_data.usage,
                                model_ref=usage_data.model.id,
                                provider_id='google',
                            ).total_price
                        )
                except Exception:
                    pass
        except Exception:  # pragma: no cover
            pass
        return attrs

    _Helper._maybe_update_token_counts = _wrapped_maybe_update_token_counts  # pyright: ignore[reportPrivateUsage]
    _Helper.create_final_attributes = _wrapped_create_final_attributes
except Exception:  # pragma: no cover
    pass


Part: TypeAlias = 'dict[str, Any] | str'


def default_json(x: Any) -> str:
    return base64.b64encode(x).decode('utf-8') if isinstance(x, bytes) else x


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

        span.add_event(record.event_name, attributes={'event_body': json.dumps(body, default=default_json)})


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
