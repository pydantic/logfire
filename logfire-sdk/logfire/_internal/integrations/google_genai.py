from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any

import logfire
from logfire._internal.integrations.llm_providers.usage import gateway_header_cost, gateway_reported_cost
from logfire._internal.stack_info import warn_at_user_stacklevel
from logfire._internal.utils import get_version, handle_internal_errors, safe_repr

CAPTURE_MESSAGE_CONTENT_ENV_VAR = 'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'
LEGACY_CAPTURE_MESSAGE_CONTENT_VALUES = {'true': 'SPAN_ONLY', 'false': 'NO_CONTENT'}
EMIT_EVENT_ENV_VAR = 'OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT'

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


def _gateway_cost(response: Any) -> float | None:
    """The cost the AI Gateway reported for a response or the final chunk of a stream, if any.

    google-genai keeps no unknown usage fields, so the gateway reports the cost of a stream in
    `part_metadata` of the last part of the first candidate in the final chunk. A non-streamed
    response has it in the `logfire-ai-gateway-cost` header, which google-genai keeps.
    """
    candidates = response.candidates or ()
    content = candidates[0].content if candidates else None
    parts = (content.parts if content else None) or ()
    if parts and (cost := gateway_reported_cost(getattr(parts[-1], 'part_metadata', None) or {})) is not None:
        return cost
    http_response = response.sdk_http_response
    return gateway_header_cost(http_response.headers if http_response else None)


with handle_internal_errors:
    from opentelemetry.instrumentation.google_genai import generate_content

    # Add the gateway cost while the SDK response and invocation attributes are both available.
    # Every streamed chunk and non-streamed response, sync or async, goes through this private hook.
    # Keep the original attribute extraction; an incompatible upstream hook is reported by Logfire's
    # internal-error handler rather than silently disabling cost recording.
    original_apply_response_attributes = generate_content._apply_response_attributes  # pyright: ignore[reportPrivateUsage]

    def wrapped_apply_response_attributes(
        response: Any, finish_reasons: Any, invocation: Any, *args: Any, **kwargs: Any
    ):
        original_apply_response_attributes(response, finish_reasons, invocation, *args, **kwargs)
        with handle_internal_errors:
            if (cost := _gateway_cost(response)) is not None:
                invocation.attributes['operation.cost'] = cost

    generate_content._apply_response_attributes = wrapped_apply_response_attributes  # pyright: ignore[reportPrivateUsage]


def _warn_if_google_genai_version_unsupported() -> None:
    """Warn loudly when the installed google-genai can't be fully instrumented.

    `opentelemetry-instrumentation-google-genai` only supports `google-genai >= 1.69.0, < 3`
    (the range the `logfire[google-genai]` extra pins). Outside it the failure is silent:
    with 3.x the upstream instrumentor logs one line and instruments nothing, so no spans,
    token counts or `operation.cost` are recorded; below 1.69.0 streamed AI Gateway costs
    (read from `part_metadata`, see #2702) are missing. A warning is used instead of
    raising so apps that call `instrument_google_genai()` unconditionally keep working.
    See https://github.com/pydantic/logfire/issues/2880.
    """
    try:
        installed_version = get_version(package_version('google-genai'))
    except PackageNotFoundError:  # pragma: no cover - google-genai is always installed here
        return
    if installed_version >= get_version('3'):
        warn_at_user_stacklevel(
            f'Logfire cannot instrument google-genai {installed_version}: '
            'opentelemetry-instrumentation-google-genai only supports google-genai >=1.69.0,<3, '
            'so no spans will be created. Pin google-genai to <3 until upstream supports 3.x, e.g. '
            "pip install 'google-genai<3'. See https://github.com/pydantic/logfire/issues/2880.",
            UserWarning,
        )
    elif installed_version < get_version('1.69.0'):
        warn_at_user_stacklevel(
            f'google-genai {installed_version} is older than 1.69.0: streamed AI Gateway costs '
            '(operation.cost) will not be recorded. Upgrade to google-genai>=1.69.0,<3.',
            UserWarning,
        )


def instrument_google_genai(logfire_instance: logfire.Logfire, **kwargs: Any):
    _warn_if_google_genai_version_unsupported()

    capture_message_content = os.getenv(CAPTURE_MESSAGE_CONTENT_ENV_VAR)
    if capture_message_content is not None:
        canonical_value = LEGACY_CAPTURE_MESSAGE_CONTENT_VALUES.get(capture_message_content.strip().lower())
        if canonical_value is not None:
            os.environ[CAPTURE_MESSAGE_CONTENT_ENV_VAR] = canonical_value

    # The instrumentation unconditionally sets OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT=true when it
    # instruments, which makes it emit a `gen_ai.client.inference.operation.details` log event alongside
    # every request span. In the span-based capture modes we use, that event is redundant (it duplicates the
    # span attributes and, without content, adds nothing). Restore the user's own setting afterwards so the
    # event follows the normal default for the content-capture mode (no event for NO_CONTENT / SPAN_ONLY).
    # Upstream issue: https://github.com/open-telemetry/opentelemetry-python-genai/issues/619
    emit_event = os.environ.get(EMIT_EVENT_ENV_VAR)

    GoogleGenAiSdkInstrumentor().instrument(
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            'logger_provider': logfire_instance.config.get_logger_provider(),
            **kwargs,
        }
    )

    if emit_event is None:
        os.environ.pop(EMIT_EVENT_ENV_VAR, None)
    else:
        os.environ[EMIT_EVENT_ENV_VAR] = emit_event
