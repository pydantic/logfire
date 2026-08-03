from __future__ import annotations

import os
from typing import Any

import logfire
from logfire._internal.utils import safe_repr

CAPTURE_MESSAGE_CONTENT_ENV_VAR = 'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'
LEGACY_CAPTURE_MESSAGE_CONTENT_VALUES = {'true': 'SPAN_ONLY', 'false': 'NO_CONTENT'}

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


def instrument_google_genai(logfire_instance: logfire.Logfire, **kwargs: Any):
    capture_message_content = os.getenv(CAPTURE_MESSAGE_CONTENT_ENV_VAR)
    if capture_message_content is not None:
        canonical_value = LEGACY_CAPTURE_MESSAGE_CONTENT_VALUES.get(capture_message_content.strip().lower())
        if canonical_value is not None:
            os.environ[CAPTURE_MESSAGE_CONTENT_ENV_VAR] = canonical_value

    GoogleGenAiSdkInstrumentor().instrument(
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        }
    )
