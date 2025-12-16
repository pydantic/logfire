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
