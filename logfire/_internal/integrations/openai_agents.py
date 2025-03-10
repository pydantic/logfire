from __future__ import annotations

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
from openai.types.responses import Response
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall
from openai.types.responses.response_output_message import ResponseOutputMessage
from typing_extensions import Self

from logfire._internal.utils import handle_internal_errors, log_internal_error

if TYPE_CHECKING:
    from agents.tracing.setup import TraceProvider
    from openai.types.responses.response_input_item_param import ResponseInputItemParam

    from logfire import Logfire, LogfireSpan


class LogfireTraceProviderWrapper:
    def __init__(self, wrapped: TraceProvider, logfire_instance: Logfire):
        self.wrapped = wrapped
        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='openai_agents')

    def create_trace(
        self,
        name: str,
        trace_id: str | None = None,
        group_id: str | None = None,
        disabled: bool = False,
    ) -> Trace:
        trace: Trace | None = None
        try:
            trace = self.wrapped.create_trace(name, trace_id, group_id, disabled)
            if isinstance(trace, NoOpTrace):
                return trace
            helper = LogfireTraceHelper(
                self.logfire_instance.span(
                    'OpenAI Agents trace {name}', name=name, agent_trace_id=trace_id, group_id=group_id
                )
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
                msg_template = 'Generation'
            elif isinstance(span_data, ResponseSpanData):
                msg_template = 'Response {response_id}'
                if span_data.response_id is None:
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
            )
            helper = LogfireTraceHelper(logfire_span)
            return LogfireSpanWrapper(span, helper)
        except Exception:
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

    @handle_internal_errors
    def on_ending(self):
        logfire_span = self.span_helper.span
        if not logfire_span.is_recording():
            return
        template = logfire_span.message_template
        assert template
        new_attrs = attributes_from_span_data(self.span_data, template)
        message = template.format(**new_attrs)
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
        return attributes
    except Exception:
        log_internal_error()
        return {}


class ResponseDataWrapper(ResponseSpanData):
    _response_id: str | None = None
    extra_attributes: dict[str, Any] = {}

    @property
    def response_id(self):
        return self._response_id

    @response_id.setter
    def response_id(self, value: str):
        self._response_id = value
        with handle_internal_errors:
            frame = inspect.currentframe()
            assert frame
            frame = frame.f_back
            assert frame
            self.extra_attributes = extra_attributes = {}
            response: Response | None = None
            for name, var in frame.f_locals.items():
                if name == 'model_settings' and isinstance(var, ModelSettings):
                    extra_attributes[name] = var
                elif name == 'self' and isinstance(var, OpenAIResponsesModel):
                    extra_attributes['gen_ai.request.model'] = var.model
                elif isinstance(var, Response) and var.id == value:
                    extra_attributes['response'] = response = var
                    extra_attributes['gen_ai.response.model'] = var.model
            extra_attributes['gen_ai.system'] = 'openai'
            extra_attributes['gen_ai.operation.name'] = 'chat'
            events: list[dict[str, Any]] = []
            if response and response.instructions:
                events += [
                    {
                        'event.name': 'gen_ai.system.message',
                        'content': response.instructions,
                        'role': 'system',
                    }
                ]
            inputs: str | None | list[ResponseInputItemParam] = frame.f_locals.get('input')
            if inputs and isinstance(inputs, str):
                inputs = [{'role': 'user', 'content': inputs}]
            if inputs:
                for inp in inputs:  # type: ignore
                    inp: dict[str, Any]
                    assert isinstance(inp, dict)
                    role: str | None = inp.get('role')
                    typ = inp.get('type')
                    content = inp.get('content')
                    if role and typ in (None, 'message') and content:
                        assert role in ('user', 'system', 'assistant')  # TODO
                        event_name = f'gen_ai.{role}.message'
                        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):  # type: ignore
                            content_text = content[0].get('text')  # type: ignore
                            if (
                                content_text
                                and isinstance(content_text, str)
                                and content == [{'annotations': [], 'text': content_text, 'type': 'output_text'}]
                            ):
                                content = content_text
                        events.append({'event.name': event_name, 'content': content, 'role': role})
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
                        events.append(
                            {
                                'event.name': 'gen_ai.unknown',
                                **inp,
                            }
                        )
            if response and response.output:
                for out in response.output:
                    if isinstance(out, ResponseOutputMessage):
                        content = out.content
                        if len(content) == 1 and content[0].type == 'output_text' and not content[0].annotations:
                            event_content = content[0].text
                        else:
                            event_content = content
                        message = {'content': event_content}
                    elif isinstance(out, ResponseFunctionToolCall):
                        message = {
                            'tool_calls': [
                                {
                                    'id': out.call_id,
                                    'type': 'function',
                                    'function': {'name': out.name, 'arguments': out.arguments},
                                },
                            ]
                        }
                    else:
                        message = out.model_dump()
                    events.append(
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {'role': 'assistant', **message},
                        },
                    )
            if events:
                extra_attributes['events'] = events
