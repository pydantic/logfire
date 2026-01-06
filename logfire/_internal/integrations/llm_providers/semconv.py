"""Gen AI Semantic Convention attribute names.

These constants follow the OpenTelemetry Gen AI Semantic Conventions.
See: https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""

from __future__ import annotations

# Provider and operation
PROVIDER_NAME = 'gen_ai.provider.name'
OPERATION_NAME = 'gen_ai.operation.name'

# Model information
REQUEST_MODEL = 'gen_ai.request.model'
RESPONSE_MODEL = 'gen_ai.response.model'

# Request parameters
REQUEST_MAX_TOKENS = 'gen_ai.request.max_tokens'
REQUEST_TEMPERATURE = 'gen_ai.request.temperature'
REQUEST_TOP_P = 'gen_ai.request.top_p'
REQUEST_TOP_K = 'gen_ai.request.top_k'
REQUEST_STOP_SEQUENCES = 'gen_ai.request.stop_sequences'
REQUEST_SEED = 'gen_ai.request.seed'
REQUEST_FREQUENCY_PENALTY = 'gen_ai.request.frequency_penalty'
REQUEST_PRESENCE_PENALTY = 'gen_ai.request.presence_penalty'

# Response metadata
RESPONSE_ID = 'gen_ai.response.id'
RESPONSE_FINISH_REASONS = 'gen_ai.response.finish_reasons'

# Token usage
INPUT_TOKENS = 'gen_ai.usage.input_tokens'
OUTPUT_TOKENS = 'gen_ai.usage.output_tokens'

# Message content
INPUT_MESSAGES = 'gen_ai.input.messages'
OUTPUT_MESSAGES = 'gen_ai.output.messages'
SYSTEM_INSTRUCTIONS = 'gen_ai.system_instructions'

# Tool definitions
TOOL_DEFINITIONS = 'gen_ai.tool.definitions'

# Conversation tracking
CONVERSATION_ID = 'gen_ai.conversation.id'
