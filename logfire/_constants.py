from typing_extensions import Literal

LOGFIRE_ATTRIBUTES_NAMESPACE = 'logfire'
"""Namespace within OTEL attributes used by logfire"""

ATTRIBUTES_ATTRIBUTES_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.attributes'
"""The key within OTEL attributes where logfire puts serialized attributes"""

LevelName = Literal['debug', 'info', 'notice', 'warning', 'error', 'critical']
"""Level names for records"""

ATTRIBUTES_LOG_LEVEL_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.level'
"""The key within OTEL attributes where logfire puts the log level"""

SpanTypeType = Literal['log', 'start_span', 'span']

SPAN_TYPE_ATTRIBUTE_NAME = 'span_type'
"""The key within OTEL attributes where logfire puts the span type"""

ATTRIBUTES_SPAN_TYPE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.{SPAN_TYPE_ATTRIBUTE_NAME}'
"""Used to differentiate logs, start spans and regular spans. Absences should be interpreted as a real span"""

ATTRIBUTES_START_SPAN_REAL_PARENT_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.start_parent_id'
"""The real parent of a start span, i.e. the parent of it's corresponding span and also it's grandparent"""

ATTRIBUTES_TAGS_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.tags'
"""The key within OTEL attributes where logfire puts tags"""

ATTRIBUTES_MESSAGE_TEMPLATE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.msg_template'
"""The message template for a log"""

ATTRIBUTES_MESSAGE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.msg'
"""The formatted message"""

ATTRIBUTES_VALIDATION_ERROR_KEY = 'exception.logfire.data'
"""The key within OTEL attributes where logfire puts validation errors"""

NON_SCALAR_VAR_SUFFIX = '__JSON'
"""Suffix added to non-scalar variables to indicate they should be serialized as JSON"""

NULL_ARGS_KEY = 'logfire.null_args'
"""Key in OTEL attributes that collects attributes with a null (None) value"""

START_SPAN_NAME_SUFFIX = ' (start)'
"""Suffix added to the name of a start span to indicate it's a start span and avoid collisions with the real span while in flight"""

LOGFIRE_API_ROOT = 'https://api.logfire.dev'
"""The root URL for the Logfire API"""
