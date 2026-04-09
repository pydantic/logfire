from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, cast

from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter

warnings.filterwarnings(
    'ignore',
    message='jsonschema.RefResolver is deprecated.*',
    category=DeprecationWarning,
)
warnings.filterwarnings(
    'ignore',
    message='Accessing jsonschema.__version__ is deprecated.*',
    category=DeprecationWarning,
)

try:
    import autogen as _autogen
except ImportError:  # pragma: no cover
    _autogen = None

autogen: Any = cast(Any, _autogen)


@dataclass
class _DummyRunResponse:
    callback: Any

    def process(self, processor: Any = None) -> None:
        self.callback()


def _new_user_proxy(name: str) -> Any:
    return autogen.UserProxyAgent(
        name=name,
        human_input_mode='NEVER',
        max_consecutive_auto_reply=10,
        code_execution_config=False,
    )


def test_instrument_ag2_conversation_groupchat_and_turn_spans(
    exporter: TestExporter,
    monkeypatch: Any,
) -> None:
    if autogen is None:  # pragma: no cover
        return

    proxy = _new_user_proxy('user_proxy')
    assistant = _new_user_proxy('assistant_agent')

    group_chat = autogen.GroupChat(agents=[proxy, assistant], messages=[], max_round=5)
    manager = autogen.GroupChatManager(groupchat=group_chat, llm_config=False)

    def fake_select_speaker(self: Any, last_speaker: Any, selector: Any) -> Any:
        return assistant

    def fake_generate_reply(
        self: Any, messages: list[dict[str, Any]] | None = None, sender: Any = None, exclude: Any = ()
    ) -> dict[str, Any]:
        return {'role': 'assistant', 'content': 'TERMINATE'}

    def fake_run_chat(
        self: Any, messages: list[dict[str, Any]] | None = None, sender: Any = None, config: Any = None
    ) -> tuple[bool, None]:
        group_chat.append({'role': 'user', 'content': 'What is AG2?'}, proxy)
        _ = group_chat.select_speaker(proxy, self)
        _ = assistant.generate_reply(messages=[{'role': 'user', 'content': 'What is AG2?'}], sender=proxy)
        group_chat.append({'role': 'assistant', 'content': 'TERMINATE'}, assistant)
        return True, None

    def fake_run(self: Any, recipient: Any = None, **kwargs: Any) -> _DummyRunResponse:
        def _process() -> None:
            recipient.run_chat(
                messages=[{'role': 'user', 'content': kwargs.get('message', '')}],
                sender=self,
                config=recipient.groupchat,
            )

        return _DummyRunResponse(callback=_process)

    monkeypatch.setattr(autogen.GroupChat, 'select_speaker', fake_select_speaker)
    monkeypatch.setattr(autogen.ConversableAgent, 'generate_reply', fake_generate_reply)
    monkeypatch.setattr(autogen.GroupChatManager, 'run_chat', fake_run_chat)
    monkeypatch.setattr(autogen.ConversableAgent, 'run', fake_run)

    with logfire.instrument_ag2(record_content=True):
        proxy.run(manager, message='What is AG2?').process()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'AG2 group chat round',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_ag2.py',
                    'code.function': 'fake_run_chat',
                    'code.lineno': 123,
                    'ag2.round_number': 1,
                    'ag2.last_speaker': 'user_proxy',
                    'logfire.msg_template': 'AG2 group chat round',
                    'logfire.msg': 'AG2 group chat round',
                    'logfire.span_type': 'span',
                    'ag2.next_speaker': 'assistant_agent',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'ag2.round_number': {}, 'ag2.last_speaker': {}, 'ag2.next_speaker': {}},
                    },
                },
            },
            {
                'name': 'AG2 agent turn',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_ag2.py',
                    'code.function': 'fake_run_chat',
                    'code.lineno': 123,
                    'ag2.agent_name': 'assistant_agent',
                    'ag2.sender_name': 'user_proxy',
                    'ag2.message_role': 'user',
                    'ag2.message_content': 'What is AG2?',
                    'logfire.msg_template': 'AG2 agent turn',
                    'logfire.msg': 'AG2 agent turn',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'ag2.agent_name': {},
                            'ag2.sender_name': {},
                            'ag2.message_role': {},
                            'ag2.message_content': {},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'AG2 group chat run',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_ag2.py',
                    'code.function': '_process',
                    'code.lineno': 123,
                    'ag2.manager_name': 'chat_manager',
                    'ag2.max_round': 5,
                    'logfire.msg_template': 'AG2 group chat run',
                    'logfire.msg': 'AG2 group chat run',
                    'logfire.span_type': 'span',
                    'ag2.groupchat.message_count': 2,
                    'ag2.groupchat.last_message_role': 'assistant',
                    'ag2.groupchat.terminated': True,
                    'ag2.groupchat.is_termination': True,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'ag2.manager_name': {},
                            'ag2.max_round': {},
                            'ag2.groupchat.message_count': {},
                            'ag2.groupchat.last_message_role': {},
                            'ag2.groupchat.terminated': {},
                            'ag2.groupchat.is_termination': {},
                        },
                    },
                },
            },
            {
                'name': 'AG2 conversation',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_ag2.py',
                    'code.function': 'test_instrument_ag2_conversation_groupchat_and_turn_spans',
                    'code.lineno': 123,
                    'ag2.runner_name': 'user_proxy',
                    'ag2.recipient_name': 'chat_manager',
                    'ag2.user_message': 'What is AG2?',
                    'logfire.msg_template': 'AG2 conversation',
                    'logfire.msg': 'AG2 conversation',
                    'logfire.span_type': 'span',
                    'ag2.total_messages': 2,
                    'ag2.total_rounds': 2,
                    'ag2.last_role': 'assistant',
                    'ag2.termination_reason': 'TERMINATE',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'ag2.runner_name': {},
                            'ag2.recipient_name': {},
                            'ag2.user_message': {},
                            'ag2.total_messages': {},
                            'ag2.total_rounds': {},
                            'ag2.last_role': {},
                            'ag2.termination_reason': {},
                        },
                    },
                },
            },
        ]
    )


def test_instrument_ag2_tool_spans(exporter: TestExporter) -> None:
    if autogen is None:  # pragma: no cover
        return

    proxy = _new_user_proxy('tool_proxy')

    @proxy.register_for_execution()
    def search_knowledge(query: str) -> str:
        return f'Results for {query}'

    _ = search_knowledge

    with logfire.instrument_ag2(record_content=True):
        success, payload = proxy.execute_function(
            {'name': 'search_knowledge', 'arguments': '{"query": "AG2"}'}, call_id='call-1'
        )

    assert success is True
    assert payload['content'] == 'Results for AG2'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'AG2 tool execution',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_ag2.py',
                    'code.function': 'test_instrument_ag2_tool_spans',
                    'code.lineno': 123,
                    'ag2.agent_name': 'tool_proxy',
                    'ag2.tool_name': 'search_knowledge',
                    'ag2.call_id': 'call-1',
                    'ag2.tool_arg_names': ['query'],
                    'ag2.tool_args': {'query': 'AG2'},
                    'logfire.msg_template': 'AG2 tool execution',
                    'logfire.msg': 'AG2 tool execution',
                    'logfire.span_type': 'span',
                    'ag2.execution.success': True,
                    'ag2.tool_result': 'Results for AG2',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'ag2.agent_name': {},
                            'ag2.tool_name': {},
                            'ag2.call_id': {},
                            'ag2.tool_arg_names': {'type': 'array'},
                            'ag2.tool_args': {'type': 'object'},
                            'ag2.execution.success': {},
                            'ag2.tool_result': {},
                        },
                    },
                },
            }
        ]
    )


def test_instrument_ag2_record_content_false_omits_message_content(
    exporter: TestExporter,
    monkeypatch: Any,
) -> None:
    if autogen is None:  # pragma: no cover
        return

    assistant = _new_user_proxy('assistant_agent')

    def fake_generate_reply(
        self: Any, messages: list[dict[str, Any]] | None = None, sender: Any = None, exclude: Any = ()
    ) -> dict[str, Any]:
        return {'role': 'assistant', 'content': 'ok'}

    monkeypatch.setattr(autogen.ConversableAgent, 'generate_reply', fake_generate_reply)

    with logfire.instrument_ag2(record_content=False):
        assistant.generate_reply(messages=[{'role': 'user', 'content': 'secret prompt'}], sender=None)

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'AG2 agent turn',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_ag2.py',
                    'code.function': 'test_instrument_ag2_record_content_false_omits_message_content',
                    'code.lineno': 123,
                    'ag2.agent_name': 'assistant_agent',
                    'ag2.message_role': 'user',
                    'logfire.msg_template': 'AG2 agent turn',
                    'logfire.msg': 'AG2 agent turn',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'ag2.agent_name': {}, 'ag2.message_role': {}},
                    },
                    'logfire.span_type': 'span',
                },
            }
        ]
    )


def test_instrument_ag2_unpatches_on_context_exit() -> None:
    if autogen is None:  # pragma: no cover
        return

    original = autogen.ConversableAgent.generate_reply

    with logfire.instrument_ag2():
        assert autogen.ConversableAgent.generate_reply is not original

    assert autogen.ConversableAgent.generate_reply is original


def test_instrument_ag2_eager_patching() -> None:
    """Calling instrument_ag2() without `with` should still apply patches immediately."""
    if autogen is None:  # pragma: no cover
        return

    original = autogen.ConversableAgent.generate_reply

    ctx = logfire.instrument_ag2()
    # Patches applied eagerly, before entering the context manager
    assert autogen.ConversableAgent.generate_reply is not original

    # Clean up by entering and exiting the context manager
    with ctx:
        pass

    assert autogen.ConversableAgent.generate_reply is original
