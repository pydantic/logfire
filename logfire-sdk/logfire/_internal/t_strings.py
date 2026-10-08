from __future__ import annotations

from string.templatelib import Template, convert

from logfire._internal.formatter import KnownFormattingError, LiteralChunk, ValueChunk


def template_chunks(format_string: Template) -> list[LiteralChunk | ValueChunk]:
    result: list[LiteralChunk | ValueChunk] = []
    for index, literal_text in enumerate(format_string.strings):
        if literal_text:
            result.append({'t': 'lit', 'v': literal_text})
        if index == len(format_string.interpolations):
            continue
        interpolation = format_string.interpolations[index]
        field_name = interpolation.expression
        try:
            formatted = convert(interpolation.value, interpolation.conversion)
        except Exception as exc:
            raise KnownFormattingError(f'Error converting field {{{field_name}}}: {exc}') from exc
        try:
            formatted = format(formatted, interpolation.format_spec)
        except Exception as exc:
            raise KnownFormattingError(f'Error formatting field {{{field_name}}}: {exc}') from exc
        result.append({'t': 'value', 'source': field_name, 'value': interpolation.value, 'formatted': formatted})
    return result


def template_to_format_string(format_string: Template) -> str:
    result = ''
    for index, literal_text in enumerate(format_string.strings):
        result += literal_text
        if index < len(format_string.interpolations):
            result += '{' + format_string.interpolations[index].expression + '}'
    return result
