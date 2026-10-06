from __future__ import annotations

from string.templatelib import Template, convert
from typing import Any

from logfire._internal.formatter import ArgChunk, ChunksFormatter, KnownFormattingError, LiteralChunk
from logfire._internal.scrubbing import BaseScrubber, MessageValueCleaner


def template_chunks(
    formatter: ChunksFormatter, format_string: Template, *, scrubber: BaseScrubber
) -> tuple[list[LiteralChunk | ArgChunk], dict[str, Any], str]:
    result: list[LiteralChunk | ArgChunk] = []
    new_template = ''
    extra_attrs: dict[str, Any] = {}
    value_cleaner = MessageValueCleaner(scrubber, check_keys=False)
    for index, literal_text in enumerate(format_string.strings):
        if literal_text:
            result.append({'v': literal_text, 't': 'lit'})
            new_template += literal_text
        if index == len(format_string.interpolations):
            continue
        interpolation = format_string.interpolations[index]
        field_name = interpolation.expression
        new_template += '{' + field_name + '}'
        extra_attrs[field_name] = interpolation.value
        try:
            value = convert(interpolation.value, interpolation.conversion)
        except Exception as exc:
            raise KnownFormattingError(f'Error converting field {{{field_name}}}: {exc}') from exc
        try:
            formatted = formatter.format_field(value, interpolation.format_spec)
        except Exception as exc:
            raise KnownFormattingError(f'Error formatting field {{{field_name}}}: {exc}') from exc
        formatted = value_cleaner.clean_value(field_name, formatted)
        result.append({'v': formatted, 't': 'arg'})
    extra_attrs.update(value_cleaner.extra_attrs())
    return result, extra_attrs, new_template


def template_to_format_string(format_string: Template) -> str:
    result = ''
    for index, literal_text in enumerate(format_string.strings):
        result += literal_text
        if index < len(format_string.interpolations):
            result += '{' + format_string.interpolations[index].expression + '}'
    return result
