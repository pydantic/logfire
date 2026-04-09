from __future__ import annotations

import argparse
import os

from autogen import AssistantAgent, GroupChat, GroupChatManager, LLMConfig, UserProxyAgent

import logfire


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the AG2 quickstart runner."""
    parser = argparse.ArgumentParser(description='AG2 + Logfire quickstart with real OpenAI calls')
    parser.add_argument(
        '--model',
        default='gpt-4o-mini',
        help='OpenAI model name (default: gpt-4o-mini)',
    )
    parser.add_argument(
        '--question',
        default='Briefly explain what AG2 is and why multi-agent orchestration helps in practice.',
        help='Task to run through AG2 group chat',
    )
    parser.add_argument(
        '--max-round',
        type=int,
        default=6,
        help='Maximum group-chat rounds (default: 6)',
    )
    return parser.parse_args()


def is_termination(msg: dict[str, object]) -> bool:
    """Return True when a message indicates the AG2 chat should terminate."""
    content = msg.get('content', '') or ''
    return isinstance(content, str) and 'TERMINATE' in content


def _extract_final_message(messages: list[dict[str, object]]) -> str | None:
    for message in reversed(messages):
        content = message.get('content')
        if not isinstance(content, str) or not content.strip():
            continue

        role = message.get('role')
        if role == 'assistant' or 'TERMINATE' in content:
            return content

    return None


def main() -> None:
    """Run a real AG2 group chat with OpenAI and emit Logfire spans."""
    args = parse_args()

    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        raise SystemExit('OPENAI_API_KEY is required to run real OpenAI calls.')

    llm_config = LLMConfig(
        {
            'model': args.model,
            'api_key': openai_api_key,
            'api_type': 'openai',
        }
    )

    send_to_logfire = bool(os.getenv('LOGFIRE_TOKEN'))
    logfire.configure(send_to_logfire=send_to_logfire)

    proxy = UserProxyAgent(
        name='user_proxy',
        human_input_mode='NEVER',
        max_consecutive_auto_reply=10,
        code_execution_config=False,
        is_termination_msg=is_termination,
    )
    researcher = AssistantAgent(
        name='researcher',
        system_message='You gather short factual context. Keep it compact.',
        llm_config=llm_config,
    )
    summarizer = AssistantAgent(
        name='summarizer',
        system_message='You summarize the answer clearly and finish with TERMINATE.',
        llm_config=llm_config,
    )

    @proxy.register_for_execution()
    @researcher.register_for_llm(description='Lookup short synthetic facts')
    def quick_lookup(topic: str) -> str:
        return f'Quick lookup result about: {topic}'

    group_chat = GroupChat(agents=[proxy, researcher, summarizer], messages=[], max_round=args.max_round)
    manager = GroupChatManager(groupchat=group_chat, llm_config=llm_config, is_termination_msg=is_termination)

    with logfire.instrument_ag2(record_content=False):
        # Optional but recommended for provider-level spans.
        logfire.instrument_openai()
        print(f'Running AG2 chat with model={args.model!r} ...')
        response = proxy.run(manager, message=args.question)
        final_output = response.process()

    if final_output is None:
        typed_messages: list[dict[str, object]] = list(manager.groupchat.messages)
        final_output = _extract_final_message(typed_messages)

    print('\n=== Final output ===\n')
    print(final_output if final_output is not None else '(No final content returned by AG2 response.process())')
    print('\nDone. Open Logfire to inspect AG2 conversation, rounds, turns, and tool spans.')


if __name__ == '__main__':
    main()
