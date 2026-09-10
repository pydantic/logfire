"""Models that record what they were asked for, so a turn can be inspected without a provider.

Two of them subclass a real plugin: the settings table is keyed on the plugin a model belongs to, and
a plugin's own constructor is the thing that fills the private options a published setting collides
with, so an imitation of one would test the imitation.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from livekit.agents import llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.plugins import anthropic, openai


@dataclass
class Request:
    """One `LLM.chat()` call, as the plugin would have seen it."""

    chat_ctx: llm.ChatContext
    tools: list[llm.Tool]
    tool_choice: NotGivenOr[llm.ToolChoice]
    parallel_tool_calls: NotGivenOr[bool]
    extra_kwargs: NotGivenOr[dict[str, Any]]
    conn_options: APIConnectOptions
    system_texts: list[str]
    """Every system message, snapshotted at call time: the framework goes on editing the same context
    afterwards -- it re-applies the code instructions to it, and appends the reply."""
    call_names: list[str]
    """The tool calls in the history, under the names the model was shown them by."""
    message_texts: list[str]
    """Every message's text, snapshotted for the same reason as `system_texts`."""

    @property
    def system_text(self) -> str | None:
        """The agent's own instructions, which LiveKit keeps as the first system message."""
        return self.system_texts[0] if self.system_texts else None

    @property
    def tool_names(self) -> list[str]:
        return [tool.info.name for tool in self.tools if isinstance(tool, (llm.FunctionTool, llm.RawFunctionTool))]

    def schema(self, name: str) -> dict[str, Any]:
        """The schema the model was shown for one advertised tool."""
        for tool in self.tools:
            if isinstance(tool, llm.RawFunctionTool) and tool.info.name == name:
                return tool.info.raw_schema
            if isinstance(tool, llm.FunctionTool) and tool.info.name == name:
                return llm.utils.build_legacy_openai_schema(tool)['function']
        raise KeyError(name)  # pragma: no cover - a test asking for a tool that was not advertised


class Recording:
    """Records every `chat()`, and answers with a scripted tool call and then a message."""

    requests: list[Request]
    tool_call: str | None

    def _start_recording(self, tool_call: str | None) -> None:
        self.requests = []
        self.tool_call = tool_call

    async def _prewarm_impl(self) -> None:
        """Do nothing. A real plugin opens a connection here, which a swap would do on every test."""
        return None

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
        **_: Any,
    ) -> llm.LLMStream:
        self.requests.append(
            Request(
                chat_ctx=chat_ctx,
                tools=list(tools or []),
                tool_choice=tool_choice,
                parallel_tool_calls=parallel_tool_calls,
                extra_kwargs=extra_kwargs,
                conn_options=conn_options,
                system_texts=[
                    item.text_content or ''
                    for item in chat_ctx.items
                    if isinstance(item, llm.ChatMessage) and item.role == 'system'
                ],
                call_names=[
                    item.name for item in chat_ctx.items if isinstance(item, (llm.FunctionCall, llm.FunctionCallOutput))
                ],
                message_texts=[item.text_content or '' for item in chat_ctx.items if isinstance(item, llm.ChatMessage)],
            )
        )
        assert isinstance(self, llm.LLM)
        return _RecordedStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class _RecordedStream(llm.LLMStream):
    async def _run(self) -> None:
        tool_call: str | None = getattr(self._llm, 'tool_call', None)
        answered = any(item.type == 'function_call_output' for item in self._chat_ctx.items)
        if tool_call and not answered:
            call = llm.FunctionToolCall(name=tool_call, arguments=json.dumps({'city': 'Paris'}), call_id='call-1')
            delta = llm.ChoiceDelta(role='assistant', tool_calls=[call])
        else:
            delta = llm.ChoiceDelta(role='assistant', content='Sunny.')
        self._event_ch.send_nowait(llm.ChatChunk(id='chunk', delta=delta))


class StubLLM(Recording, llm.LLM):
    """A model belonging to no plugin family, which is what a community plugin looks like from here."""

    def __init__(self, *, tool_call: str | None = None, model: str = 'stub-1') -> None:
        llm.LLM.__init__(self)
        self._start_recording(tool_call)
        self._name = model

    @property
    def model(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return 'stub'


class StubOpenAILLM(Recording, openai.LLM):  # pyright: ignore[reportIncompatibleMethodOverride]
    """The real OpenAI plugin, with the request captured instead of sent.

    The recorded `chat()` answers with the base `LLMStream` rather than the plugin's own, which is the
    point: nothing about a captured request is OpenAI-shaped.
    """

    def __init__(self, *, tool_call: str | None = None, **kwargs: Any) -> None:
        openai.LLM.__init__(self, **kwargs)
        self._start_recording(tool_call)


class StubAnthropicLLM(Recording, anthropic.LLM):  # pyright: ignore[reportIncompatibleMethodOverride]
    """The real Anthropic plugin, with the request captured instead of sent."""

    def __init__(self, *, tool_call: str | None = None, **kwargs: Any) -> None:
        anthropic.LLM.__init__(self, **kwargs)
        self._start_recording(tool_call)


@dataclass
class RealtimeUpdates:
    """What a realtime session was told, which is all an adapter can reach on that path."""

    instructions: list[str] = field(default_factory=list[str])
    tools: list[list[llm.Tool]] = field(default_factory=list['list[llm.Tool]'])


class StubRealtimeModel(llm.RealtimeModel):
    """A realtime model whose session records the updates the adapter sends it."""

    def __init__(self, *, mutable_instructions: bool = True, mutable_tools: bool = True) -> None:
        super().__init__(
            capabilities=llm.RealtimeCapabilities(
                message_truncation=False,
                turn_detection=False,
                user_transcription=False,
                auto_tool_reply_generation=False,
                audio_output=False,
                manual_function_calls=False,
                mutable_chat_context=True,
                mutable_instructions=mutable_instructions,
                mutable_tools=mutable_tools,
            )
        )
        self.updates = RealtimeUpdates()

    @property
    def model(self) -> str:
        return 'stub-realtime'

    @property
    def provider(self) -> str:
        return 'stub'

    def session(self, *, turn_detection_disabled: bool = False) -> llm.RealtimeSession:
        return _StubRealtimeSession(self)

    async def aclose(self) -> None:  # pragma: no cover - inert
        return None


class _StubRealtimeSession(llm.RealtimeSession):
    """A session that records the two updates an adapter can send it.

    The rest of `RealtimeSession` is abstract and has to be here for the class to exist at all; a
    text-only test never pushes audio or generates a reply through it, so those are left inert.
    """

    def __init__(self, model: StubRealtimeModel) -> None:
        super().__init__(model)
        self.updates = model.updates
        self._chat_ctx = llm.ChatContext.empty()
        self._tools = llm.ToolContext.empty()

    @property
    def chat_ctx(self) -> llm.ChatContext:  # pragma: no cover - inert
        return self._chat_ctx

    @property
    def tools(self) -> llm.ToolContext:  # pragma: no cover - inert
        return self._tools

    async def update_instructions(self, instructions: str) -> None:
        self.updates.instructions.append(instructions)

    async def update_chat_ctx(self, chat_ctx: llm.ChatContext) -> None:
        self._chat_ctx = chat_ctx

    async def update_tools(self, tools: list[llm.Tool]) -> None:
        self.updates.tools.append(list(tools))
        self._tools = llm.ToolContext(tools)

    def push_audio(self, frame: Any) -> None:  # pragma: no cover - inert
        return None

    def push_video(self, frame: Any) -> None:  # pragma: no cover - inert
        return None

    def generate_reply(self, **kwargs: Any) -> Any:  # pragma: no cover - inert
        raise NotImplementedError

    def commit_audio(self) -> None:  # pragma: no cover - inert
        return None

    def clear_audio(self) -> None:  # pragma: no cover - inert
        return None

    def interrupt(self) -> None:  # pragma: no cover - inert
        return None

    def truncate(self, **kwargs: Any) -> None:  # pragma: no cover - inert
        return None

    def update_options(self, **kwargs: Any) -> None:  # pragma: no cover - inert
        return None

    async def aclose(self) -> None:  # pragma: no cover - inert
        return None

    def __aiter__(self) -> AsyncIterator[Any]:  # pragma: no cover - inert
        raise NotImplementedError
