"""Reference-syntax Handlebars: low-level primitives for ``@{}@`` rendering.

This module provides ``render_once`` which performs a single-pass render using
``@{}@`` as the delimiter instead of ``{{}}``. It is the engine behind variable
composition — it gives ``@{}@`` syntax a Handlebars-compatible subset while
preserving any ``{{}}`` runtime placeholders untouched.

Algorithm:
  a. Protect ``{{...}}`` runtime placeholders in the template
  b. Convert ``@{...}@`` reference tags to standard Handlebars ``{{...}}`` tags
  c. Run standard Handlebars
  d. Restore the protected runtime placeholders
  e. Unescape entities introduced to protect context values
"""

from __future__ import annotations

import re
from typing import Any

from logfire.variables._handlebars import get_handlebars_renderer

_REFERENCE_TAG = re.compile(r'(?<!\\)@\{(.*?)\}@')
_ESCAPED_REFERENCE_START = r'\@{'


def _sentinel(name: str, template: str) -> str:
    """Return a per-template sentinel unlikely to collide with user content."""
    return f'\x00logfire-{name}-{id(template)}\x00'


def _protect_value(value: Any, safe_string_cls: type[str]) -> Any:
    """Recursively mark string values safe, preserving structure for dicts/lists."""
    if isinstance(value, str):
        return safe_string_cls(value)
    if isinstance(value, dict):
        return {k: _protect_value(v, safe_string_cls) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [_protect_value(v, safe_string_cls) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value  # bools, ints, None, etc. — pass through


# ---------------------------------------------------------------------------
# Core single-pass render: protect runtime placeholders → convert refs → render
# ---------------------------------------------------------------------------


def render_once(template: str, context: dict[str, Any]) -> str:
    """Single-pass render: convert ``@{}@`` tags, run Handlebars, restore ``{{}}``."""
    safe_string_cls, hbs_render = get_handlebars_renderer()
    left_runtime_placeholder = _sentinel('left-runtime-placeholder', template)
    right_runtime_placeholder = _sentinel('right-runtime-placeholder', template)
    escaped_reference_start = _sentinel('escaped-reference-start', template)
    protected_template = (
        template.replace(_ESCAPED_REFERENCE_START, escaped_reference_start)
        .replace('{{', left_runtime_placeholder)
        .replace('}}', right_runtime_placeholder)
    )
    handlebars_template = _REFERENCE_TAG.sub(r'{{\1}}', protected_template)
    safe_context = {k: _protect_value(v, safe_string_cls) for k, v in context.items()}
    result: str = hbs_render(handlebars_template, safe_context)
    return (
        result.replace(left_runtime_placeholder, '{{')
        .replace(right_runtime_placeholder, '}}')
        .replace(escaped_reference_start, '@{')
    )
