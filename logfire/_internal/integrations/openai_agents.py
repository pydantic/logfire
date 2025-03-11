from __future__ import annotations

import contextlib
import contextvars
import inspect
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
    ModelSettings,
    Span,
    SpanError,
    Trace,
)
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tracing import ResponseSpanData
from agents.tracing.scope import Scope
from agents.tracing.spans import NoOpSpan, SpanData, TSpanData
from agents.tracing.traces import NoOpTrace
from typing_extensions import Self

from logfire._internal.formatter import logfire_format
from logfire._internal.scrubbing import NOOP_SCRUBBER
from logfire._internal.utils import handle_internal_errors, log_internal_error

if TYPE_CHECKING:  # pragma: no cover
    from agents.tracing.setup import TraceProvider
    from openai.types.responses import Response

    from logfire import Logfire, LogfireSpan


class LogfireTraceProviderWrapper:
    def __init__(self, wrapped: TraceProvider, logfire_instance: Logfire):
        self.wrapped = wrapped
        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='openai_agents')

    def create_trace(
        self,
        name: str,
        trace_id: str | None = None,
        disabled: bool = False,
        **kwargs: Any,
    ) -> Trace:
        trace: Trace | None = None
        try:
            trace = self.wrapped.create_trace(name, trace_id=trace_id, disabled=disabled, **kwargs)
            if isinstance(trace, NoOpTrace):
                return trace
            helper = LogfireSpanHelper(
                self.logfire_instance.span('OpenAI Agents trace: {name}', name=name, agent_trace_id=trace_id, **kwargs)
            )
            return LogfireTraceWrapper(trace, helper)
        except Exception:  # pragma: no cover
            log_internal_error()
            return trace or NoOpTrace()

    def create_span(
        self,
        span_data: TSpanData,
        span_id: str | None = None,
        parent: Trace | Span[Any] | None = None,
        disabled: bool = False,
    ) -> Span[TSpanData]:
        span: Span[TSpanData] | None = None
        try:
            span = self.wrapped.create_span(span_data, span_id, parent, disabled)
            if isinstance(span, NoOpSpan):
                return span

            if isinstance(span_data, AgentSpanData):
                msg_template = 'Agent {name}'
            elif isinstance(span_data, FunctionSpanData):
                msg_template = 'Function {name}'
            elif isinstance(span_data, GenerationSpanData):
                msg_template = 'Chat completion with {gen_ai.request.model!r}'
            elif isinstance(span_data, ResponseSpanData):
                msg_template = 'Responses API'
                span_data.__class__ = ResponseDataWrapper
            elif isinstance(span_data, GuardrailSpanData):
                msg_template = 'Guardrail {name} triggered={triggered}'
            elif isinstance(span_data, HandoffSpanData):
                msg_template = 'Handoff {from_agent} -> {to_agent}'
            elif isinstance(span_data, CustomSpanData):
                msg_template = 'Custom span: {name}'
            else:
                msg_template = 'OpenAI agents {type} span'

            logfire_span = self.logfire_instance.span(
                msg_template,
                **attributes_from_span_data(span_data, msg_template),
                _tags=['LLM'] * isinstance(span_data, GenerationSpanData),
            )
            helper = LogfireSpanHelper(logfire_span)
            return LogfireSpanWrapper(span, helper)
        except Exception:  # pragma: no cover
            log_internal_error()
            return span or NoOpSpan(span_data)

    def __getattr__(self, item: Any) -> Any:
        return getattr(self.wrapped, item)

    @classmethod
    def install(cls, logfire_instance: Logfire) -> None:
        name = 'GLOBAL_TRACE_PROVIDER'
        original = getattr(agents.tracing, name)
        if isinstance(original, cls):
            return
        wrapper = cls(original, logfire_instance)
        for module_name, mod in sys.modules.items():
            if module_name.startswith('agents'):
                try:
                    if getattr(mod, name, None) is original:
                        setattr(mod, name, wrapper)
                except Exception:  # pragma: no cover
                    pass


@dataclass
class LogfireSpanHelper:
    span: LogfireSpan

    def start(self, mark_as_current: bool):
        self.span._start()  # type: ignore
        if mark_as_current:
            self.span._attach()  # type: ignore

    def end(self, reset_current: bool):
        self.span._end()  # type: ignore
        self.maybe_detach(reset_current)

    def maybe_detach(self, reset_current: bool):
        if reset_current:
            self.span._detach()  # type: ignore

    def __enter__(self):
        self.start(True)

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.span.__exit__(exc_type, exc_val, exc_tb)
        self.maybe_detach(exc_type is not GeneratorExit)


@dataclass
class LogfireTraceWrapper(Trace):
    wrapped: Trace
    span_helper: LogfireSpanHelper
    token: contextvars.Token[Trace | None] | None = None

    def start(self, mark_as_current: bool = False):
        self.span_helper.start(mark_as_current)
        if mark_as_current:
            self.attach()
        return self.wrapped.start()

    def finish(self, reset_current: bool = False):
        self.on_ending()
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
        self.on_ending()
        self.span_helper.__exit__(exc_type, exc_val, exc_tb)
        self.wrapped.finish()
        if exc_type is not GeneratorExit:
            self.detach()

    @handle_internal_errors
    def on_ending(self):
        logfire_span = self.span_helper.span
        if not logfire_span.is_recording():
            return
        new_attrs = dict(agent_trace_id=self.trace_id)
        if group_id := getattr(self, 'group_id', None):
            new_attrs['group_id'] = group_id
        logfire_span.set_attributes(new_attrs)

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
    wrapped: Span[TSpanData]
    span_helper: LogfireSpanHelper
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

    @handle_internal_errors
    def on_ending(self):
        logfire_span = self.span_helper.span
        if not logfire_span.is_recording():
            return
        template = logfire_span.message_template
        assert template
        new_attrs = attributes_from_span_data(self.span_data, template)
        if 'gen_ai.request.model' not in template and 'gen_ai.request.model' in new_attrs:
            template += ' with {gen_ai.request.model!r}'
        try:
            message = logfire_format(template, new_attrs, NOOP_SCRUBBER)
        except Exception:  # pragma: no cover
            message = logfire_span.message
        if error := self.error:
            new_attrs['error'] = error
            message += f' failed: {error["message"]}'
            logfire_span.set_level('error')
        logfire_span.message = message
        logfire_span.set_attributes(new_attrs)

    @property
    def parent_id(self) -> str | None:
        return self.wrapped.parent_id

    def set_error(self, error: SpanError) -> None:
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


def attributes_from_span_data(span_data: SpanData, msg_template: str) -> dict[str, Any]:
    try:
        attributes = span_data.export()
        if '{type}' not in msg_template and attributes.get('type') == span_data.type:
            del attributes['type']
        if isinstance(span_data, ResponseDataWrapper):
            attributes.update(span_data.extra_attributes)
            if span_data.input:
                attributes['raw_input'] = span_data.input
            if events := get_response_span_events(span_data):
                attributes['events'] = events
            if (usage := getattr(span_data.response, 'usage', None)) and getattr(usage, 'total_tokens', None):
                attributes['gen_ai.usage.input_tokens'] = usage.input_tokens
                attributes['gen_ai.usage.output_tokens'] = usage.output_tokens
        elif isinstance(span_data, GenerationSpanData):
            attributes['request_data'] = dict(
                messages=list(span_data.input or []) + list(span_data.output or []), model=span_data.model
            )
            attributes.update(
                {
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': span_data.model,
                    'gen_ai.response.model': span_data.model,
                    # Having this makes it try to generate the new chat panel and fail
                    # 'gen_ai.operation.name': 'chat',
                }
            )
            del attributes['model']
            if usage := span_data.usage:
                attributes['gen_ai.usage.input_tokens'] = usage['input_tokens']
                attributes['gen_ai.usage.output_tokens'] = usage['output_tokens']
        return attributes
    except Exception:  # pragma: no cover
        log_internal_error()
        return {}


class ResponseDataWrapper(ResponseSpanData):
    # TODO reduce the magic here
    _response: Response | None = None
    extra_attributes: dict[str, Any] = {}

    @property
    def response(self):
        return self._response

    @response.setter
    def response(self, response: Response):
        self._response = response
        with handle_internal_errors:
            frame = inspect.currentframe()
            assert frame
            frame = frame.f_back
            assert frame
            self.extra_attributes = {
                'gen_ai.response.model': getattr(response, 'model', None),
                'response': response,
                'gen_ai.system': 'openai',
                'gen_ai.operation.name': 'chat',
            }
            for name, var in frame.f_locals.items():
                if name == 'model_settings' and isinstance(var, ModelSettings):
                    self.extra_attributes[name] = var
                elif name == 'self' and isinstance(var, OpenAIResponsesModel):
                    self.extra_attributes['gen_ai.request.model'] = var.model


@handle_internal_errors
def get_response_span_events(span: ResponseSpanData):
    events: list[dict[str, Any]] = []
    response = span.response
    inputs = span.input
    if response and (instructions := getattr(response, 'instructions', None)):
        events += [
            {
                'event.name': 'gen_ai.system.message',
                'content': instructions,
                'role': 'system',
            }
        ]
    if inputs:
        if isinstance(inputs, str):  # pragma: no cover
            inputs = [{'role': 'user', 'content': inputs}]
        for inp in inputs:  # type: ignore
            inp: dict[str, Any]
            events += input_to_events(inp)
    if response and response.output:
        for out in response.output:
            for message in input_to_events(out.model_dump()):
                message.pop('event.name', None)
                events.append(
                    {
                        'event.name': 'gen_ai.choice',
                        'index': 0,
                        'message': {**message, 'role': 'assistant'},
                    },
                )
    return events


def input_to_events(inp: dict[str, Any]):
    try:
        events: list[dict[str, Any]] = []
        role: str | None = inp.get('role')
        typ = inp.get('type')
        content = inp.get('content')
        if role and typ in (None, 'message') and content:
            event_name = f'gen_ai.{role}.message'
            if isinstance(content, str):
                events.append({'event.name': event_name, 'content': content, 'role': role})
            else:
                for content_item in content:
                    with contextlib.suppress(KeyError):
                        if content_item['type'] == 'output_text':  # pragma: no branch
                            events.append({'event.name': event_name, 'content': content_item['text'], 'role': role})
                            continue
                    events.append(unknown_event(content_item))  # pragma: no cover
        elif typ == 'function_call':
            events.append(
                {
                    'event.name': 'gen_ai.assistant.message',
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': inp['call_id'],
                            'type': 'function',
                            'function': {'name': inp['name'], 'arguments': inp['arguments']},
                        },
                    ],
                }
            )
        elif typ == 'function_call_output':
            events.append(
                {
                    'event.name': 'gen_ai.tool.message',
                    'role': 'tool',
                    'id': inp['call_id'],
                    'content': inp['output'],
                }
            )
        else:
            events.append(unknown_event(inp))
        return events
    except Exception:  # pragma: no cover
        log_internal_error()
        return [unknown_event(inp)]


def unknown_event(inp: dict[str, Any]):
    return {
        'event.name': 'gen_ai.unknown',
        'role': inp.get('role') or 'unknown',
        'content': f'{inp.get("type")}\n\nSee JSON for details',
        'data': inp,
    }
