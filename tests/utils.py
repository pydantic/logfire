from __future__ import annotations

import asyncio
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel

from logfire.testing import TestExporter


@contextmanager
def event_loop_policy(policy: asyncio.AbstractEventLoopPolicy) -> Generator[None, None, None]:
    previous_policy = asyncio.get_event_loop_policy()  # pyright: ignore[reportDeprecated]
    asyncio.set_event_loop_policy(policy)  # pyright: ignore[reportDeprecated]
    try:
        yield
    finally:
        asyncio.set_event_loop_policy(previous_policy)  # pyright: ignore[reportDeprecated]


@contextmanager
def current_event_loop(loop: asyncio.AbstractEventLoop) -> Generator[None, None, None]:
    """Temporarily set a loop on Python 3.14+, where get_event_loop() never creates one."""
    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None

    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        asyncio.set_event_loop(previous_loop)


@contextmanager
def isolated_litellm_event_loop_context() -> Generator[None, None, None]:
    """Give LiteLLM a loop owned by this test without disturbing an existing loop."""
    if sys.version_info >= (3, 14):
        loop = asyncio.new_event_loop()
        try:
            with current_event_loop(loop):
                yield
        finally:
            loop.close()
        return

    test_policy = asyncio.DefaultEventLoopPolicy()
    with event_loop_policy(test_policy):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            yield
        finally:
            loop.close()


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
