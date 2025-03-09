from __future__ import annotations

import contextvars
import sys
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any

import agents
from agents import (
    AgentSpanData,
    CustomSpanData,
    FunctionSpanData,
    GenerationSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    Span,
    SpanError,
    Trace,
)
from agents.tracing.scope import Scope
from agents.tracing.spans import NoOpSpan, SpanData, TSpanData
from agents.tracing.traces import NoOpTrace
from typing_extensions import Self

if TYPE_CHECKING:
    from agents.tracing.setup import TraceProvider

    from logfire import Logfire, LogfireSpan


class LogfireTraceProviderWrapper:
    def __init__(self, wrapped: TraceProvider, logfire_instance: Logfire):
        self.wrapped = wrapped
        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='openai_agents')

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
        helper = LogfireTraceHelper(
            self.logfire_instance.span(
                'OpenAI Agents trace {name}', name=name, agent_trace_id=trace_id, agent_session_id=session_id
            )
        )
        return LogfireTraceWrapper(trace, helper)

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
        if isinstance(span_data, AgentSpanData):
            msg_template = 'Agent {agent_name}'
        elif isinstance(span_data, FunctionSpanData):
            msg_template = 'Function {name}'
        elif isinstance(span_data, GenerationSpanData):
            msg_template = 'Generation response_id={response_id} input={input}'
        elif isinstance(span_data, GuardrailSpanData):
            msg_template = 'Guardrail {name} triggered={triggered}'
        elif isinstance(span_data, HandoffSpanData):
            msg_template = 'Handoff {from_agent} -> {to_agent}'
        elif isinstance(span_data, CustomSpanData):
            msg_template = 'Custom span: {display_name}'
        else:
            msg_template = 'OpenAI agents {type} span'
        logfire_span = self.logfire_instance.span(
            msg_template,
            **attributes_from_span_data(span_data, msg_template),
        )
        helper = LogfireTraceHelper(logfire_span)
        return LogfireSpanWrapper(span, helper)

    def __getattr__(self, item: Any) -> Any:
        return getattr(self.wrapped, item)

    @classmethod
    def install(cls, logfire_instance: Logfire) -> None:
        name = 'GLOBAL_TRACE_PROVIDER'
        original = getattr(agents.tracing, name)
        if isinstance(original, cls):
            return
        wrapper = cls(original, logfire_instance)
        for mod in sys.modules.values():
            try:
                if getattr(mod, name, None) is original:
                    setattr(mod, name, wrapper)
            except Exception:
                pass


@dataclass
class LogfireTraceHelper:
    span: LogfireSpan

    def start(self, mark_as_current: bool):
        self.span.start()
        if mark_as_current:
            self.span.attach()

    def end(self, reset_current: bool):
        self.span.end()
        self.maybe_detach(reset_current)

    def maybe_detach(self, reset_current: bool):
        if reset_current:
            self.span.detach()

    def __enter__(self):
        self.start(True)

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.span.__exit__(exc_type, exc_val, exc_tb)
        self.maybe_detach(exc_type is not GeneratorExit)


@dataclass
class LogfireSpanHelper:
    span_data: SpanData


@dataclass
class LogfireTraceWrapper(Trace):
    wrapped: Trace
    span_helper: LogfireTraceHelper
    token: contextvars.Token[Trace | None] | None = None

    def start(self, mark_as_current: bool = False):
        self.span_helper.start(mark_as_current)
        if mark_as_current:
            self.attach()
        return self.wrapped.start()

    def finish(self, reset_current: bool = False):
        self.span_helper.end(reset_current)
        if reset_current:
            self.detach()
        return self.wrapped.finish()

    def __enter__(self) -> Trace:
        self.span_helper.__enter__()
        self.wrapped.start()
        self.attach()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.span_helper.__exit__(exc_type, exc_val, exc_tb)
        self.wrapped.finish()
        if exc_type is not GeneratorExit:
            self.detach()

    def attach(self):
        self.token = Scope.set_current_trace(self)

    def detach(self):
        if self.token:
            Scope.reset_current_trace(self.token)
            self.token = None

    @property
    def trace_id(self) -> str:
        return self.wrapped.trace_id

    @property
    def name(self) -> str:
        return self.wrapped.name

    def export(self) -> dict[str, Any] | None:
        return self.wrapped.export()

    def __getattr__(self, item: str):
        return getattr(self.wrapped, item)


@dataclass
class LogfireSpanWrapper(Span[TSpanData]):
    __slots__ = ('wrapped', 'span_helper')

    wrapped: Span[TSpanData]
    span_helper: LogfireTraceHelper
    token: contextvars.Token[Span[TSpanData] | None] | None = None

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
        if mark_as_current:
            self.attach()
        return self.wrapped.start()

    def finish(self, reset_current: bool = False) -> None:
        self.on_ending()
        self.span_helper.end(reset_current)
        if reset_current:
            self.detach()
        return self.wrapped.finish()

    def __enter__(self) -> Self:
        self.span_helper.__enter__()
        self.wrapped.start()
        self.attach()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.on_ending()
        self.span_helper.__exit__(exc_type, exc_val, exc_tb)
        self.wrapped.finish()
        if exc_type is not GeneratorExit:
            self.detach()

    def attach(self):
        self.token = Scope.set_current_span(self)

    def detach(self):
        if self.token:
            Scope.reset_current_span(self.token)
            self.token = None

    def on_ending(self):
        logfire_span = self.span_helper.span
        if logfire_span.is_recording():
            template = logfire_span.message_template
            assert template
            new_attrs = attributes_from_span_data(self.span_data, template)
            logfire_span.message = template.format(**new_attrs)
            logfire_span.set_attributes(new_attrs)

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


def attributes_from_span_data(span_data: SpanData, msg_template: str):
    attributes = span_data.export()
    if '{type}' not in msg_template and attributes.get('type') == span_data.type:
        del attributes['type']
    return attributes
