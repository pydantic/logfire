from _typeshed import Incomplete
from claude_agent_sdk import AssistantMessage
from claude_agent_sdk.types import HookContext, SyncHookJSONOutput
from contextlib import AbstractContextManager
from logfire._internal.integrations.llm_providers.semconv import CONVERSATION_ID as CONVERSATION_ID, ChatMessage as ChatMessage, ERROR_TYPE as ERROR_TYPE, INPUT_MESSAGES as INPUT_MESSAGES, MessagePart as MessagePart, OPERATION_NAME as OPERATION_NAME, OUTPUT_MESSAGES as OUTPUT_MESSAGES, OutputMessage as OutputMessage, PROVIDER_NAME as PROVIDER_NAME, REQUEST_MODEL as REQUEST_MODEL, RESPONSE_MODEL as RESPONSE_MODEL, ReasoningPart as ReasoningPart, SYSTEM as SYSTEM, SYSTEM_INSTRUCTIONS as SYSTEM_INSTRUCTIONS, TOOL_CALL_ARGUMENTS as TOOL_CALL_ARGUMENTS, TOOL_CALL_ID as TOOL_CALL_ID, TOOL_CALL_RESULT as TOOL_CALL_RESULT, TOOL_NAME as TOOL_NAME, TextPart as TextPart, ToolCallPart as ToolCallPart, ToolCallResponsePart as ToolCallResponsePart
from logfire._internal.main import Logfire as Logfire, LogfireSpan as LogfireSpan
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from typing import Any

async def pre_tool_use_hook(input_data: Any, tool_use_id: str | None, _context: HookContext) -> SyncHookJSONOutput:
    """Create a child span when a tool execution starts."""
async def post_tool_use_hook(input_data: Any, tool_use_id: str | None, _context: HookContext) -> SyncHookJSONOutput:
    """End the tool span after successful execution."""
async def post_tool_use_failure_hook(input_data: Any, tool_use_id: str | None, _context: HookContext) -> SyncHookJSONOutput:
    """End the tool span with an error after failed execution."""
def instrument_claude_agent_sdk(logfire_instance: Logfire) -> AbstractContextManager[None]:
    """Instrument the Claude Agent SDK by monkey-patching ClaudeSDKClient.

    Returns:
        A context manager that will revert the instrumentation when exited.
            This context manager doesn't take into account threads or other concurrency.
            Calling this function will immediately apply the instrumentation
            without waiting for the context manager to be opened,
            i.e. it's not necessary to use this as a context manager.
    """

class _ConversationState:
    """Per-conversation state stored in thread-local during a receive_response iteration.

    Holds everything hooks need: the root span, logfire instance, active tool spans,
    chat span lifecycle, and conversation history. This keeps all mutable state in one
    object instead of scattered across globals and thread-local attributes.
    """
    logfire: Incomplete
    root_span: Incomplete
    active_tool_spans: dict[str, LogfireSpan]
    model: str | None
    def __init__(self, *, logfire: Logfire, root_span: LogfireSpan, input_messages: list[ChatMessage], system_instructions: list[TextPart] | None = None) -> None: ...
    def add_tool_result(self, tool_use_id: str, tool_name: str, result: Any) -> None:
        """Record a tool result to include in the next chat span's input messages."""
    def open_chat_span(self) -> None:
        """Open a new chat span — call when the LLM starts processing."""
    def close_chat_span(self) -> None:
        """Close the current chat span without opening a new one.

        Safe to call from hooks (different async contexts) because chat spans
        are never entered into the OTel context stack.
        """
    def handle_user_message(self) -> None:
        """Handle UserMessage: open a new chat span for the next LLM call."""
    def handle_assistant_message(self, message: AssistantMessage) -> None:
        """Handle AssistantMessage: add output and usage to the current chat span."""
    def close(self) -> None:
        """Close chat span and end any orphaned tool spans."""
