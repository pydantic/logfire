from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, contextmanager, nullcontext
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from logfire import Logfire
from logfire._internal.utils import suppress_instrumentation

if TYPE_CHECKING:  # pragma: no cover
    from autogen import ConversableAgent


try:
    import autogen
except ImportError:  # pragma: no cover
    raise RuntimeError(
        '`logfire.instrument_ag2()` requires the `ag2` package.\n'
        'You can install this with:\n'
        "    pip install 'ag2[openai]>=0.11.4,<1.0'"
    )

SPAN_CONVERSATION = 'AG2 conversation'
SPAN_GROUPCHAT = 'AG2 group chat run'
SPAN_GROUPCHAT_ROUND = 'AG2 group chat round'
SPAN_AGENT_TURN = 'AG2 agent turn'
SPAN_TOOL_EXECUTION = 'AG2 tool execution'


def instrument_ag2(
    logfire_instance: Logfire,
    agent: ConversableAgent | Iterable[ConversableAgent] | None = None,
    *,
    record_content: bool = False,
    suppress_other_instrumentation: bool = False,
) -> AbstractContextManager[None]:
    """Instrument AG2 conversations, agent turns, and tool execution.

    See ``Logfire.instrument_ag2`` for full documentation.
    """
    target_ids = _target_agent_ids(agent)
    originals: list[tuple[object, str, Any]] = []

    def should_trace(agent_obj: Any) -> bool:
        return target_ids is None or id(agent_obj) in target_ids

    def patch(
        cls_or_obj: object, method_name: str, wrapper_factory: Callable[[Callable[..., Any]], Callable[..., Any]]
    ) -> None:
        original = getattr(cls_or_obj, method_name, None)
        if original is None:
            return
        wrapped = wrapper_factory(original)
        setattr(cls_or_obj, method_name, wrapped)
        originals.append((cls_or_obj, method_name, original))

    def wrap_run(original: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(original)
        def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            response = original(self, *args, **kwargs)
            if not should_trace(self):
                return response
            _wrap_response_process(
                response=response,
                logfire_instance=logfire_instance,
                runner=self,
                recipient=_resolve_recipient(args, kwargs),
                message=kwargs.get('message'),
                record_content=record_content,
                suppress_other_instrumentation=suppress_other_instrumentation,
            )
            return response

        return _wrapped

    def wrap_a_run(original: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(original)
        async def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            response = await original(self, *args, **kwargs)
            if not should_trace(self):
                return response
            _wrap_response_process(
                response=response,
                logfire_instance=logfire_instance,
                runner=self,
                recipient=_resolve_recipient(args, kwargs),
                message=kwargs.get('message'),
                record_content=record_content,
                suppress_other_instrumentation=suppress_other_instrumentation,
            )
            return response

        return _wrapped

    def wrap_generate_reply(original: Callable[..., Any]) -> Callable[..., Any]:
        # generate_reply(self, messages=None, sender=None, exclude=())
        @wraps(original)
        def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            messages = args[0] if len(args) > 0 else kwargs.get('messages')
            sender = args[1] if len(args) > 1 else kwargs.get('sender')
            attrs = _agent_turn_attrs(self, sender, messages, record_content)
            with logfire_instance.span(SPAN_AGENT_TURN, **attrs):
                return original(self, *args, **kwargs)

        return _wrapped

    def wrap_a_generate_reply(original: Callable[..., Any]) -> Callable[..., Any]:
        # a_generate_reply(self, messages=None, sender=None, exclude=())
        @wraps(original)
        async def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            messages = args[0] if len(args) > 0 else kwargs.get('messages')
            sender = args[1] if len(args) > 1 else kwargs.get('sender')
            attrs = _agent_turn_attrs(self, sender, messages, record_content)
            with logfire_instance.span(SPAN_AGENT_TURN, **attrs):
                return await original(self, *args, **kwargs)

        return _wrapped

    def wrap_execute_function(original: Callable[..., Any]) -> Callable[..., Any]:
        # execute_function(self, func_call, call_id=None, verbose=False)
        @wraps(original)
        def _wrapped(self: Any, func_call: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            call_id = args[0] if len(args) > 0 else kwargs.get('call_id')
            attrs = _tool_call_attrs(self, func_call, call_id, record_content)
            with logfire_instance.span(SPAN_TOOL_EXECUTION, **attrs) as span:
                result = original(self, func_call, *args, **kwargs)
                _set_tool_result_attributes(span, result, record_content)
                return result

        return _wrapped

    def wrap_a_execute_function(original: Callable[..., Any]) -> Callable[..., Any]:
        # a_execute_function(self, func_call, call_id=None, verbose=False)
        @wraps(original)
        async def _wrapped(self: Any, func_call: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            call_id = args[0] if len(args) > 0 else kwargs.get('call_id')
            attrs = _tool_call_attrs(self, func_call, call_id, record_content)
            with logfire_instance.span(SPAN_TOOL_EXECUTION, **attrs) as span:
                result = await original(self, func_call, *args, **kwargs)
                _set_tool_result_attributes(span, result, record_content)
                return result

        return _wrapped

    def wrap_run_chat(original: Callable[..., Any]) -> Callable[..., Any]:
        # run_chat(self, messages=None, sender=None, config=None)
        @wraps(original)
        def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            groupchat = args[2] if len(args) > 2 else kwargs.get('config')
            attrs = {
                'ag2.manager_name': getattr(self, 'name', type(self).__name__),
                'ag2.max_round': getattr(groupchat, 'max_round', None),
            }
            attrs = {k: v for k, v in attrs.items() if v is not None}
            with logfire_instance.span(SPAN_GROUPCHAT, **attrs) as span:  # pyright: ignore[reportArgumentType]
                result = original(self, *args, **kwargs)
                _set_groupchat_summary_attributes(span, groupchat, self)
                return result

        return _wrapped

    def wrap_a_run_chat(original: Callable[..., Any]) -> Callable[..., Any]:
        # a_run_chat(self, messages=None, sender=None, config=None)
        @wraps(original)
        async def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            groupchat = args[2] if len(args) > 2 else kwargs.get('config')
            attrs = {
                'ag2.manager_name': getattr(self, 'name', type(self).__name__),
                'ag2.max_round': getattr(groupchat, 'max_round', None),
            }
            attrs = {k: v for k, v in attrs.items() if v is not None}
            with logfire_instance.span(SPAN_GROUPCHAT, **attrs) as span:  # pyright: ignore[reportArgumentType]
                result = await original(self, *args, **kwargs)
                _set_groupchat_summary_attributes(span, groupchat, self)
                return result

        return _wrapped

    def wrap_select_speaker(original: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(original)
        def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            attrs = {
                'ag2.round_number': len(getattr(self, 'messages', []) or []),
                'ag2.last_speaker': getattr(args[0], 'name', None) if args else None,
            }
            attrs = {k: v for k, v in attrs.items() if v is not None}
            with logfire_instance.span(SPAN_GROUPCHAT_ROUND, **attrs) as span:  # pyright: ignore[reportArgumentType]
                selected = original(self, *args, **kwargs)
                span.set_attribute('ag2.next_speaker', getattr(selected, 'name', type(selected).__name__))
                return selected

        return _wrapped

    def wrap_a_select_speaker(original: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(original)
        async def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            attrs = {
                'ag2.round_number': len(getattr(self, 'messages', []) or []),
                'ag2.last_speaker': getattr(args[0], 'name', None) if args else None,
            }
            attrs = {k: v for k, v in attrs.items() if v is not None}
            with logfire_instance.span(SPAN_GROUPCHAT_ROUND, **attrs) as span:  # pyright: ignore[reportArgumentType]
                selected = await original(self, *args, **kwargs)
                span.set_attribute('ag2.next_speaker', getattr(selected, 'name', type(selected).__name__))
                return selected

        return _wrapped

    patch(autogen.ConversableAgent, 'run', wrap_run)
    patch(autogen.ConversableAgent, 'a_run', wrap_a_run)
    patch(autogen.ConversableAgent, 'generate_reply', wrap_generate_reply)
    patch(autogen.ConversableAgent, 'a_generate_reply', wrap_a_generate_reply)
    patch(autogen.ConversableAgent, 'execute_function', wrap_execute_function)
    patch(autogen.ConversableAgent, 'a_execute_function', wrap_a_execute_function)

    patch(autogen.GroupChatManager, 'run_chat', wrap_run_chat)
    patch(autogen.GroupChatManager, 'a_run_chat', wrap_a_run_chat)

    patch(autogen.GroupChat, 'select_speaker', wrap_select_speaker)
    patch(autogen.GroupChat, 'a_select_speaker', wrap_a_select_speaker)

    @contextmanager
    def uninstrument_context():
        # The user isn't required (or even expected) to use this context manager,
        # which is why the instrumenting and patching has already happened before this point.
        # It exists mostly for tests, and just in case users want it.
        try:
            yield
        finally:
            for cls_or_obj, method_name, orig in reversed(originals):
                setattr(cls_or_obj, method_name, orig)

    return uninstrument_context()


def _wrap_response_process(
    *,
    response: Any,
    logfire_instance: Logfire,
    runner: Any,
    recipient: Any,
    message: Any,
    record_content: bool,
    suppress_other_instrumentation: bool,
) -> None:
    process = getattr(response, 'process', None)
    if process is None:
        return

    if getattr(response, '_logfire_ag2_process_wrapped', False):
        return

    wrapped: Callable[..., Any]

    if inspect.iscoroutinefunction(process):

        @wraps(process)
        async def wrapped_process_async(*args: Any, **kwargs: Any) -> Any:
            cm = suppress_instrumentation() if suppress_other_instrumentation else nullcontext()
            with cm:
                attrs = _conversation_attrs(runner, recipient, message, record_content)
                with logfire_instance.span(SPAN_CONVERSATION, **attrs) as span:
                    result = await process(*args, **kwargs)
                    _set_conversation_summary_attributes(span, recipient)
                    return result

        wrapped = wrapped_process_async

    else:

        @wraps(process)
        def wrapped_process_sync(*args: Any, **kwargs: Any) -> Any:
            cm = suppress_instrumentation() if suppress_other_instrumentation else nullcontext()
            with cm:
                attrs = _conversation_attrs(runner, recipient, message, record_content)
                with logfire_instance.span(SPAN_CONVERSATION, **attrs) as span:
                    result = process(*args, **kwargs)
                    _set_conversation_summary_attributes(span, recipient)
                    return result

        wrapped = wrapped_process_sync

    setattr(response, 'process', wrapped)
    setattr(response, '_logfire_ag2_process_wrapped', True)


def _target_agent_ids(agent: ConversableAgent | Iterable[ConversableAgent] | None) -> set[int] | None:
    if agent is None:
        return None
    if isinstance(agent, autogen.ConversableAgent):
        return {id(agent)}
    return {id(a) for a in agent}


def _resolve_recipient(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any | None:
    if 'recipient' in kwargs:
        return kwargs['recipient']
    if args:
        return args[0]
    return None


def _conversation_attrs(runner: Any, recipient: Any, message: Any, record_content: bool) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        'ag2.runner_name': getattr(runner, 'name', type(runner).__name__),
        'ag2.recipient_name': getattr(recipient, 'name', type(recipient).__name__) if recipient is not None else None,
    }
    if record_content and message is not None:
        attrs['ag2.user_message'] = _safe_content(message)
    return {k: v for k, v in attrs.items() if v is not None}


def _agent_turn_attrs(agent: Any, sender: Any, messages: Any, record_content: bool) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        'ag2.agent_name': getattr(agent, 'name', type(agent).__name__),
        'ag2.sender_name': getattr(sender, 'name', type(sender).__name__) if sender is not None else None,
    }
    last_message = _last_message(messages)
    if isinstance(last_message, dict):
        role = last_message.get('role')
        if role is not None:
            attrs['ag2.message_role'] = role
        if record_content and 'content' in last_message:
            attrs['ag2.message_content'] = _safe_content(last_message.get('content'))
    return {k: v for k, v in attrs.items() if v is not None}


def _tool_call_attrs(agent: Any, func_call: dict[str, Any], call_id: Any, record_content: bool) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        'ag2.agent_name': getattr(agent, 'name', type(agent).__name__),
        'ag2.tool_name': func_call.get('name', ''),
        'ag2.call_id': call_id,
    }
    parsed_args = _parse_tool_arguments(func_call.get('arguments'))
    attrs['ag2.tool_arg_names'] = sorted(parsed_args)
    if record_content:
        attrs['ag2.tool_args'] = parsed_args
    return {k: v for k, v in attrs.items() if v is not None}


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return cast(dict[str, Any], arguments)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        except Exception:
            return {}
    return {}


def _set_tool_result_attributes(span: Any, result: Any, record_content: bool) -> None:
    tuple_result = cast(tuple[Any, ...], result)
    if not isinstance(result, tuple) or len(tuple_result) != 2:
        return
    success, payload = cast(tuple[Any, Any], result)
    span.set_attribute('ag2.execution.success', bool(success))
    if record_content and isinstance(payload, dict):
        payload_dict = cast(dict[str, Any], payload)
        span.set_attribute('ag2.tool_result', _safe_content(payload_dict.get('content')))


def _set_groupchat_summary_attributes(span: Any, groupchat: Any, manager: Any) -> None:
    messages = getattr(groupchat, 'messages', None)
    if isinstance(messages, list) and all(isinstance(m, dict) for m in cast(list[Any], messages)):
        typed_messages = cast(list[dict[str, Any]], messages)
        span.set_attribute('ag2.groupchat.message_count', len(typed_messages))
        if typed_messages:
            last_message = typed_messages[-1]
            content = last_message.get('content', '')
            span.set_attribute('ag2.groupchat.last_message_role', last_message.get('role', 'unknown'))
            if isinstance(content, str):
                span.set_attribute('ag2.groupchat.terminated', 'TERMINATE' in content)
    if (
        isinstance(messages, list)
        and messages
        and hasattr(manager, '_is_termination_msg')
        and callable(manager._is_termination_msg)
    ):
        try:
            span.set_attribute('ag2.groupchat.is_termination', bool(manager._is_termination_msg(messages[-1])))
        except Exception:
            pass


def _set_conversation_summary_attributes(span: Any, recipient: Any) -> None:
    groupchat = getattr(recipient, 'groupchat', None)
    if groupchat is None:
        return
    messages = getattr(groupchat, 'messages', None)
    if not (isinstance(messages, list) and all(isinstance(m, dict) for m in cast(list[Any], messages))):
        return
    typed_messages = cast(list[dict[str, Any]], messages)
    span.set_attribute('ag2.total_messages', len(typed_messages))
    if typed_messages:
        rounds = _count_rounds(typed_messages)
        span.set_attribute('ag2.total_rounds', rounds)
        last = typed_messages[-1]
        role = last.get('role')
        if role is not None:
            span.set_attribute('ag2.last_role', role)
        content = last.get('content')
        if isinstance(content, str):
            span.set_attribute('ag2.termination_reason', 'TERMINATE' if 'TERMINATE' in content else 'unknown')


def _count_rounds(messages: list[dict[str, Any]]) -> int:
    """Count rounds as speaker transitions (consecutive messages from different 'name' fields)."""
    rounds = 1 if messages else 0
    for i in range(1, len(messages)):
        if messages[i].get('name') != messages[i - 1].get('name'):
            rounds += 1
    return rounds


def _last_message(messages: Any) -> dict[str, Any] | None:
    if isinstance(messages, list) and messages and isinstance(messages[-1], dict):
        return cast(dict[str, Any], messages[-1])
    return None


def _safe_content(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)
