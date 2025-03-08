from __future__ import annotations

import sys
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable

import agents
from agents import Span, SpanError, Trace
from agents.tracing.spans import NoOpSpan, TSpanData
from agents.tracing.traces import NoOpTrace
from opentelemetry import context as context_api
from opentelemetry.trace import (
    _SPAN_KEY,  # type: ignore
    Span as OtelSpan,
    TracerProvider,
    get_tracer_provider,
)

if TYPE_CHECKING:
    from agents.tracing.setup import TraceProvider


class OpenTelemetryTraceProviderWrapper:
    def __init__(self, wrapped: TraceProvider, tracer_provider: TracerProvider | None = None):
        tracer_provider = tracer_provider or get_tracer_provider()
        self.tracer = tracer_provider.get_tracer('openai.agents')
        self.wrapped = wrapped

    def create_trace(
        self,
        name: str,
        trace_id: str | None = None,
        session_id: str | None = None,
        disabled: bool = False,
    ) -> Trace:
        trace = self.wrapped.create_trace(name, trace_id, session_id, disabled)
        if isinstance(trace, NoOpTrace):
            return trace
        helper = OpenTelemetrySpanHelper(lambda: self.tracer.start_span(name))
        return OpenTelemetryTraceWrapper(trace, helper)

    def create_span(
        self,
        span_data: TSpanData,
        span_id: str | None = None,
        parent: Trace | Span[Any] | None = None,
        disabled: bool = False,
    ) -> Span[TSpanData]:
        span = self.wrapped.create_span(span_data, span_id, parent, disabled)
        if isinstance(span, NoOpSpan):
            return span
        helper = OpenTelemetrySpanHelper(lambda: self.tracer.start_span(span_data.type))
        return OpenTelemetrySpanWrapper(span, helper)

    def __getattr__(self, item: Any) -> Any:
        return getattr(self.wrapped, item)

    @classmethod
    def install(cls, tracer_provider: TracerProvider | None = None) -> None:
        name = 'GLOBAL_TRACE_PROVIDER'
        original = getattr(agents.tracing, name)
        if isinstance(original, cls):
            return
        wrapper = cls(original, tracer_provider)
        for mod in sys.modules.values():
            try:
                if getattr(mod, name, None) is original:
                    setattr(mod, name, wrapper)
            except Exception:
                pass


@dataclass
class OpenTelemetrySpanHelper:
    start_span: Callable[[], OtelSpan]
    span: OtelSpan | None = None
    token: object = None

    def start(self, mark_as_current: bool):
        if self.span:
            return
        self.span = self.start_span()
        if mark_as_current:
            self.token = context_api.attach(context_api.set_value(_SPAN_KEY, self.span))

    def end(self, reset_current: bool):
        if self.span:
            self.span.end()
            self.span = None
        self.maybe_detach(reset_current)

    def maybe_detach(self, reset_current: bool):
        if reset_current and self.token:
            context_api.detach(self.token)

    def __enter__(self):
        self.start(True)

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        if self.span:
            self.span.__exit__(exc_type, exc_val, exc_tb)
            self.span = None
        self.maybe_detach(exc_type is not GeneratorExit)


@dataclass
class OpenTelemetryTraceWrapper(Trace):
    wrapped: Trace
    span_helper: OpenTelemetrySpanHelper

    def start(self, mark_as_current: bool = False):
        self.span_helper.start(mark_as_current)
        return self.wrapped.start(mark_as_current)

    def finish(self, reset_current: bool = False):
        self.span_helper.end(reset_current)
        return self.wrapped.finish(reset_current)

    def __enter__(self) -> Trace:
        self.span_helper.__enter__()
        return self.wrapped.__enter__()

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.span_helper.__exit__(exc_type, exc_val, exc_tb)
        return self.wrapped.__exit__(exc_type, exc_val, exc_tb)  # type: ignore

    @property
    def trace_id(self) -> str:
        return self.wrapped.trace_id

    @property
    def name(self) -> str:
        return self.wrapped.name

    def export(self) -> dict[str, Any] | None:
        return self.wrapped.export()


@dataclass
class OpenTelemetrySpanWrapper(Span[TSpanData]):
    __slots__ = ('wrapped', 'span_helper')

    wrapped: Span[TSpanData]
    span_helper: OpenTelemetrySpanHelper

    @property
    def trace_id(self) -> str:
        return self.wrapped.trace_id

    @property
    def span_id(self) -> str:
        return self.wrapped.span_id

    @property
    def span_data(self) -> TSpanData:
        return self.wrapped.span_data

    def start(self, mark_as_current: bool = False):
        self.span_helper.start(mark_as_current)
        return self.wrapped.start(mark_as_current)

    def finish(self, reset_current: bool = False) -> None:
        self.span_helper.end(reset_current)
        return self.wrapped.finish(reset_current)

    def __enter__(self) -> Span[TSpanData]:
        self.span_helper.__enter__()
        return type(self.wrapped).__enter__(self)

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.span_helper.__exit__(exc_type, exc_val, exc_tb)
        return type(self.wrapped).__exit__(self, exc_type, exc_val, exc_tb)  # type: ignore

    @property
    def parent_id(self) -> str | None:
        return self.wrapped.parent_id

    def set_error(self, error: SpanError) -> None:
        # TODO
        return self.wrapped.set_error(error)

    @property
    def error(self) -> SpanError | None:
        return self.wrapped.error

    def export(self) -> dict[str, Any] | None:
        return self.wrapped.export()

    @property
    def started_at(self) -> str | None:
        return self.wrapped.started_at

    @property
    def ended_at(self) -> str | None:
        return self.wrapped.ended_at

    def __getattr__(self, item: str):
        return getattr(self.wrapped, item)

    def __setattr__(self, key: str, value: Any):
        if key in self.__slots__:
            return super().__setattr__(key, value)
        return setattr(self.wrapped, key, value)
