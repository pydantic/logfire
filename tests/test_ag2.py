from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, cast

import logfire
from logfire._internal.exporters.test import TestExporter

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

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    names = [span['name'] for span in spans]
    assert 'AG2 conversation' in names
    assert 'AG2 group chat run' in names
    assert 'AG2 group chat round' in names
    assert 'AG2 agent turn' in names

    conversation_span = next(span for span in spans if span['name'] == 'AG2 conversation')
    assert conversation_span['attributes']['ag2.runner_name'] == 'user_proxy'
    assert conversation_span['attributes']['ag2.recipient_name'] == manager.name
    assert conversation_span['attributes']['ag2.user_message'] == 'What is AG2?'


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

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    tool_span = next(span for span in spans if span['name'] == 'AG2 tool execution')
    assert tool_span['attributes']['ag2.tool_name'] == 'search_knowledge'
    assert tool_span['attributes']['ag2.call_id'] == 'call-1'
    assert tool_span['attributes']['ag2.tool_args'] == {'query': 'AG2'}
    assert tool_span['attributes']['ag2.tool_result'] == 'Results for AG2'


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

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    turn_span = next(span for span in spans if span['name'] == 'AG2 agent turn')
    assert 'ag2.message_content' not in turn_span['attributes']


def test_instrument_ag2_unpatches_on_context_exit() -> None:
    if autogen is None:  # pragma: no cover
        return

    original = autogen.ConversableAgent.generate_reply

    with logfire.instrument_ag2():
        assert autogen.ConversableAgent.generate_reply is not original

    assert autogen.ConversableAgent.generate_reply is original
