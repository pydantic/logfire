from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from logfire.testing import TestExporter


def exported_spans_as_models(
    exporter: TestExporter,
    fixed_line_number: int | None = 123,
    strip_filepaths: bool = True,
    include_resources: bool = False,
    _include_pending_spans: bool = False,
    _strip_function_qualname: bool = True,
) -> list[ReadableSpanModel]:
    """Same as exported_spans_as_dict but converts the dicts to pydantic models.

    This allows using the result in exporters that expect `ReadableSpan`s, not dicts.
    """
    return [
        ReadableSpanModel(**span)
        for span in exporter.exported_spans_as_dict(
            fixed_line_number=fixed_line_number,
            strip_filepaths=strip_filepaths,
            include_resources=include_resources,
            _include_pending_spans=_include_pending_spans,
            _strip_function_qualname=_strip_function_qualname,
        )
    ]


class SpanContextModel(BaseModel):
    """A pydantic model similar to an opentelemetry SpanContext."""

    trace_id: int
    span_id: int
    is_remote: bool


class ReadableSpanModel(BaseModel):
    """A pydantic model similar to an opentelemetry ReadableSpan."""

    name: str
    context: SpanContextModel
    parent: SpanContextModel | None
    start_time: int
    end_time: int
    attributes: dict[str, Any] | None
    events: list[dict[str, Any]] | None = None
    resource: dict[str, Any] | None = None
