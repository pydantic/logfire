from inline_snapshot import snapshot

from logfire._internal.exporters.processor_wrapper import _transform_langsmith_span_attributes  # type: ignore


# Testing this properly is too much of a pain, we'd need to create a clever mock transport or something.
# Can't use VCR because the HTTP requests happen in a different claude process.
# Testing _transform_langsmith_span_attributes covers the actual relevant changes.
def test_instrument_claude_agent_sdk():
    assert _transform_langsmith_span_attributes(
        {
            'logfire.span_type': 'span',
            'logfire.msg': 'claude.assistant.turn',
            'langsmith.span.kind': 'llm',
            'langsmith.trace.name': 'claude.assistant.turn',
            'langsmith.trace.session_name': 'default',
            'gen_ai.operation.name': 'chat',
            'gen_ai.system': 'anthropic',
            'gen_ai.request.model': 'claude-sonnet-4-5-20250929',
            'langsmith.metadata.ls_model_name': 'claude-sonnet-4-5-20250929',
            'langsmith.metadata.LANGSMITH_OTEL_ENABLED': 'true',
            'langsmith.metadata.LANGSMITH_OTEL_ONLY': 'true',
            'langsmith.metadata.LANGSMITH_TRACING': 'true',
            'langsmith.metadata.revision_id': 'v4.16.0-27-g1badd367-dirty',
            'gen_ai.serialized.name': 'claude.assistant.turn',
            'gen_ai.prompt': '{"messages":[{"content":"What\'s the weather like in Berlin?","role":"user"},{"content":[{"type":"tool_use","id":"toolu_012C5v8vaaTnK3WqX9FHhvmE","name":"mcp__weather__get_weather","input":{"city":"Berlin"}}],"role":"assistant"},{"role":"tool","content":"Weather in Berlin: Cloudy, 59°F","tool_call_id":"toolu_012C5v8vaaTnK3WqX9FHhvmE"}]}',
            'gen_ai.completion': '{"content":[{"type":"text","text":"The weather in Berlin is currently **cloudy** with a temperature of **59°F** (about 15°C). It\'s a fairly mild day! If you\'re planning to go out, you might want to bring a light jacket. Is there anything else you\'d like to know about Berlin or any other destination?"}],"role":"assistant"}',
        },
        {
            'gen_ai.prompt': {
                'messages': [
                    {'content': "What's the weather like in Berlin?", 'role': 'user'},
                    {
                        'content': [
                            {
                                'type': 'tool_use',
                                'id': 'toolu_012C5v8vaaTnK3WqX9FHhvmE',
                                'name': 'mcp__weather__get_weather',
                                'input': {'city': 'Berlin'},
                            }
                        ],
                        'role': 'assistant',
                    },
                    {
                        'role': 'tool',
                        'content': 'Weather in Berlin: Cloudy, 59°F',
                        'tool_call_id': 'toolu_012C5v8vaaTnK3WqX9FHhvmE',
                    },
                ]
            },
            'gen_ai.completion': {
                'content': [
                    {
                        'type': 'text',
                        'text': "The weather in Berlin is currently **cloudy** with a temperature of **59°F** (about 15°C). It's a fairly mild day! If you're planning to go out, you might want to bring a light jacket. Is there anything else you'd like to know about Berlin or any other destination?",
                    }
                ],
                'role': 'assistant',
            },
        },
    ) == snapshot(
        (
            {
                'logfire.span_type': 'span',
                'logfire.msg': 'claude.assistant.turn',
                'langsmith.span.kind': 'llm',
                'langsmith.trace.name': 'claude.assistant.turn',
                'langsmith.trace.session_name': 'default',
                'gen_ai.operation.name': 'chat',
                'gen_ai.system': 'anthropic',
                'gen_ai.request.model': 'claude-sonnet-4-5-20250929',
                'langsmith.metadata.ls_model_name': 'claude-sonnet-4-5-20250929',
                'langsmith.metadata.LANGSMITH_OTEL_ENABLED': 'true',
                'langsmith.metadata.LANGSMITH_OTEL_ONLY': 'true',
                'langsmith.metadata.LANGSMITH_TRACING': 'true',
                'langsmith.metadata.revision_id': 'v4.16.0-27-g1badd367-dirty',
                'gen_ai.serialized.name': 'claude.assistant.turn',
                'gen_ai.prompt': '{"messages":[{"content":"What\'s the weather like in Berlin?","role":"user"},{"content":[{"type":"tool_use","id":"toolu_012C5v8vaaTnK3WqX9FHhvmE","name":"mcp__weather__get_weather","input":{"city":"Berlin"}}],"role":"assistant"},{"role":"tool","content":"Weather in Berlin: Cloudy, 59°F","tool_call_id":"toolu_012C5v8vaaTnK3WqX9FHhvmE"}]}',
                'gen_ai.completion': '{"content":[{"type":"text","text":"The weather in Berlin is currently **cloudy** with a temperature of **59°F** (about 15°C). It\'s a fairly mild day! If you\'re planning to go out, you might want to bring a light jacket. Is there anything else you\'d like to know about Berlin or any other destination?"}],"role":"assistant"}',
            },
            {
                'gen_ai.system': 'anthropic',
                'gen_ai.provider.name': 'anthropic',
                'all_messages_events': '[{"content": "What\'s the weather like in Berlin?", "role": "user"}, {"content": [{"type": "tool_use", "id": "toolu_012C5v8vaaTnK3WqX9FHhvmE", "name": "mcp__weather__get_weather", "input": {"city": "Berlin"}}], "role": "assistant"}, {"role": "tool", "content": "Weather in Berlin: Cloudy, 59\\u00b0F", "id": "toolu_012C5v8vaaTnK3WqX9FHhvmE", "name": ""}, {"content": [{"type": "text", "text": "The weather in Berlin is currently **cloudy** with a temperature of **59\\u00b0F** (about 15\\u00b0C). It\'s a fairly mild day! If you\'re planning to go out, you might want to bring a light jacket. Is there anything else you\'d like to know about Berlin or any other destination?"}], "role": "assistant"}]',
            },
        )
    )
    assert _transform_langsmith_span_attributes(
        {
            'logfire.span_type': 'span',
            'logfire.msg': 'claude.assistant.turn',
            'gen_ai.operation.name': 'chat',
            'gen_ai.serialized.name': 'claude.assistant.turn',
            'langsmith.span.kind': 'llm',
            'langsmith.trace.name': 'claude.assistant.turn',
            'langsmith.trace.session_name': 'default',
            'gen_ai.system': 'anthropic',
            'gen_ai.request.model': 'claude-sonnet-4-5-20250929',
            'langsmith.metadata.ls_model_name': 'claude-sonnet-4-5-20250929',
            'langsmith.metadata.LANGSMITH_OTEL_ENABLED': 'true',
            'langsmith.metadata.LANGSMITH_OTEL_ONLY': 'true',
            'langsmith.metadata.LANGSMITH_TRACING': 'true',
            'langsmith.metadata.revision_id': 'v4.16.0-27-g1badd367-dirty',
            'gen_ai.prompt': '{"messages":[{"content":"What\'s the weather like in Berlin?","role":"user"}]}',
            'gen_ai.completion': '{"content":[{"type":"tool_use","id":"toolu_012C5v8vaaTnK3WqX9FHhvmE","name":"mcp__weather__get_weather","input":{"city":"Berlin"}}],"role":"assistant"}',
        },
        {
            'gen_ai.prompt': {'messages': [{'content': "What's the weather like in Berlin?", 'role': 'user'}]},
            'gen_ai.completion': {
                'content': [
                    {
                        'type': 'tool_use',
                        'id': 'toolu_012C5v8vaaTnK3WqX9FHhvmE',
                        'name': 'mcp__weather__get_weather',
                        'input': {'city': 'Berlin'},
                    }
                ],
                'role': 'assistant',
            },
        },
    ) == snapshot(
        (
            {
                'logfire.span_type': 'span',
                'logfire.msg': 'claude.assistant.turn',
                'gen_ai.operation.name': 'chat',
                'gen_ai.serialized.name': 'claude.assistant.turn',
                'langsmith.span.kind': 'llm',
                'langsmith.trace.name': 'claude.assistant.turn',
                'langsmith.trace.session_name': 'default',
                'gen_ai.system': 'anthropic',
                'gen_ai.request.model': 'claude-sonnet-4-5-20250929',
                'langsmith.metadata.ls_model_name': 'claude-sonnet-4-5-20250929',
                'langsmith.metadata.LANGSMITH_OTEL_ENABLED': 'true',
                'langsmith.metadata.LANGSMITH_OTEL_ONLY': 'true',
                'langsmith.metadata.LANGSMITH_TRACING': 'true',
                'langsmith.metadata.revision_id': 'v4.16.0-27-g1badd367-dirty',
                'gen_ai.prompt': '{"messages":[{"content":"What\'s the weather like in Berlin?","role":"user"}]}',
                'gen_ai.completion': '{"content":[{"type":"tool_use","id":"toolu_012C5v8vaaTnK3WqX9FHhvmE","name":"mcp__weather__get_weather","input":{"city":"Berlin"}}],"role":"assistant"}',
            },
            {
                'gen_ai.system': 'anthropic',
                'gen_ai.provider.name': 'anthropic',
                'all_messages_events': '[{"content": "What\'s the weather like in Berlin?", "role": "user"}, {"content": [{"type": "tool_use", "id": "toolu_012C5v8vaaTnK3WqX9FHhvmE", "name": "mcp__weather__get_weather", "input": {"city": "Berlin"}}], "role": "assistant"}]',
            },
        )
    )
    assert _transform_langsmith_span_attributes(
        {
            'logfire.span_type': 'span',
            'logfire.msg': 'claude.conversation',
            'gen_ai.operation.name': 'chain',
            'langsmith.span.kind': 'chain',
            'langsmith.trace.name': 'claude.conversation',
            'langsmith.trace.session_name': 'default',
            'gen_ai.system': 'langchain',
            'langsmith.metadata.ls_method': 'trace',
            'langsmith.metadata.num_turns': 2,
            'langsmith.metadata.session_id': '7862f9ce-d63d-4667-924d-2bbe9af293c6',
            'langsmith.metadata.duration_ms': 7617,
            'langsmith.metadata.duration_api_ms': 17992,
            'langsmith.metadata.is_error': False,
            'langsmith.metadata.LANGSMITH_OTEL_ENABLED': 'true',
            'langsmith.metadata.LANGSMITH_OTEL_ONLY': 'true',
            'langsmith.metadata.LANGSMITH_TRACING': 'true',
            'langsmith.metadata.revision_id': 'v4.16.0-27-g1badd367-dirty',
            'gen_ai.prompt': '{"prompt":"What\'s the weather like in Berlin?","system":"You are a friendly travel assistant who helps with weather information."}',
            'gen_ai.completion': '{"content":[{"type":"text","text":"The weather in Berlin is currently **cloudy** with a temperature of **59°F** (about 15°C). It\'s a fairly mild day! If you\'re planning to go out, you might want to bring a light jacket. Is there anything else you\'d like to know about Berlin or any other destination?"}],"role":"assistant"}',
        },
        {
            'gen_ai.prompt': {
                'prompt': "What's the weather like in Berlin?",
                'system': 'You are a friendly travel assistant who helps with weather information.',
            },
            'gen_ai.completion': {
                'content': [
                    {
                        'type': 'text',
                        'text': "The weather in Berlin is currently **cloudy** with a temperature of **59°F** (about 15°C). It's a fairly mild day! If you're planning to go out, you might want to bring a light jacket. Is there anything else you'd like to know about Berlin or any other destination?",
                    }
                ],
                'role': 'assistant',
            },
        },
    ) == snapshot(
        (
            {
                'logfire.span_type': 'span',
                'logfire.msg': 'claude.conversation',
                'gen_ai.operation.name': 'chain',
                'langsmith.span.kind': 'chain',
                'langsmith.trace.name': 'claude.conversation',
                'langsmith.trace.session_name': 'default',
                'langsmith.metadata.ls_method': 'trace',
                'langsmith.metadata.num_turns': 2,
                'langsmith.metadata.session_id': '7862f9ce-d63d-4667-924d-2bbe9af293c6',
                'langsmith.metadata.duration_ms': 7617,
                'langsmith.metadata.duration_api_ms': 17992,
                'langsmith.metadata.is_error': False,
                'langsmith.metadata.LANGSMITH_OTEL_ENABLED': 'true',
                'langsmith.metadata.LANGSMITH_OTEL_ONLY': 'true',
                'langsmith.metadata.LANGSMITH_TRACING': 'true',
                'langsmith.metadata.revision_id': 'v4.16.0-27-g1badd367-dirty',
                'gen_ai.prompt': '{"prompt":"What\'s the weather like in Berlin?","system":"You are a friendly travel assistant who helps with weather information."}',
                'gen_ai.completion': '{"content":[{"type":"text","text":"The weather in Berlin is currently **cloudy** with a temperature of **59°F** (about 15°C). It\'s a fairly mild day! If you\'re planning to go out, you might want to bring a light jacket. Is there anything else you\'d like to know about Berlin or any other destination?"}],"role":"assistant"}',
            },
            {
                'all_messages_events': '[{"role": "system", "content": "You are a friendly travel assistant who helps with weather information."}, {"role": "user", "content": "What\'s the weather like in Berlin?"}, {"content": [{"type": "text", "text": "The weather in Berlin is currently **cloudy** with a temperature of **59\\u00b0F** (about 15\\u00b0C). It\'s a fairly mild day! If you\'re planning to go out, you might want to bring a light jacket. Is there anything else you\'d like to know about Berlin or any other destination?"}], "role": "assistant"}]'
            },
        )
    )
