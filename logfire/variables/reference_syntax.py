"""Reference-syntax Handlebars: low-level primitives for ``@{}@`` rendering.

This module provides ``render_once`` which performs a single-pass render using
``@{}@`` as the delimiter instead of ``{{}}``. It is the engine behind variable
composition — it gives ``@{}@`` syntax the full power of Handlebars
(conditionals, loops, helpers, etc.) while preserving any ``{{}}`` runtime
placeholders untouched.

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
_LEFT_RUNTIME_PLACEHOLDER = '&#123;&#123;'
_RIGHT_RUNTIME_PLACEHOLDER = '&#125;&#125;'

# ---------------------------------------------------------------------------
# Protection: escape {} in values to numeric entities so rendered values can't
# be interpreted as Handlebars syntax during this composition pass.
# ---------------------------------------------------------------------------
_PROTECT = str.maketrans(
    {
        '{': '&#123;',
        '}': '&#125;',
    }
)


def _unescape_protected(s: str) -> str:
    """Undo only the entities we introduced."""
    return s.replace('&#123;', '{').replace('&#125;', '}')


def _protect_value(value: Any, safe_string_cls: type[str]) -> Any:
    """Recursively protect string values, preserving structure for dicts/lists."""
    if isinstance(value, str):
        return safe_string_cls(value.translate(_PROTECT))
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
    protected_template = template.replace('{{', _LEFT_RUNTIME_PLACEHOLDER).replace('}}', _RIGHT_RUNTIME_PLACEHOLDER)
    handlebars_template = _REFERENCE_TAG.sub(r'{{\1}}', protected_template)
    safe_context = {k: _protect_value(v, safe_string_cls) for k, v in context.items()}
    result: str = hbs_render(handlebars_template, safe_context)
    result = result.replace(_LEFT_RUNTIME_PLACEHOLDER, '{{').replace(_RIGHT_RUNTIME_PLACEHOLDER, '}}')
    return _unescape_protected(result).replace('\\@{', '@{')
