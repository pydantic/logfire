"""Angle-bracket Handlebars: low-level swap primitives for <<>> rendering.

This module provides ``render_once`` which performs a single-pass render using
``<<>>`` as the delimiter instead of ``{{}}``. It is the engine behind variable
composition — it gives ``<<>>`` syntax the full power of Handlebars
(conditionals, loops, helpers, etc.) while preserving any ``{{}}`` runtime
placeholders untouched.

Algorithm (swap + protect):
  a. Protect ``{}<>`` characters in context values with HTML entities
  b. Swap ``{↔<`` and ``}↔>`` in the template (so ``<<>>`` becomes ``{{}}``)
  c. Run standard Handlebars
  d. Reverse swap
  e. Unescape the entities we introduced
"""

from __future__ import annotations

from typing import Any

from logfire.handlebars import SafeString, render as hbs_render

# ---------------------------------------------------------------------------
# Character swap table: { ↔ < and } ↔ >
# ---------------------------------------------------------------------------
_SWAP = str.maketrans('{}<>', '<>{}')

# ---------------------------------------------------------------------------
# Protection: escape {}<> in values to numeric entities that contain
# NO {}<> characters, so the reverse swap can't corrupt them.
# ---------------------------------------------------------------------------
_PROTECT = str.maketrans(
    {
        '{': '&#123;',
        '}': '&#125;',
        '<': '&#60;',
        '>': '&#62;',
    }
)


def _unescape_protected(s: str) -> str:
    """Undo only the four entities we introduced."""
    return s.replace('&#123;', '{').replace('&#125;', '}').replace('&#60;', '<').replace('&#62;', '>')


def _protect_value(value: Any) -> Any:
    """Recursively protect string values, preserving structure for dicts/lists."""
    if isinstance(value, str):
        return SafeString(value.translate(_PROTECT))
    if isinstance(value, dict):
        return {k: _protect_value(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [_protect_value(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value  # bools, ints, None, etc. — pass through


# ---------------------------------------------------------------------------
# Core single-pass render: swap → Handlebars → unswap → unescape
# ---------------------------------------------------------------------------


def render_once(template: str, context: dict[str, Any]) -> str:
    """Single-pass render: swap <<>>↔{{}}, run Handlebars, reverse swap, unescape."""
    swapped_template = template.translate(_SWAP)
    safe_context = {k: _protect_value(v) for k, v in context.items()}
    result: str = hbs_render(swapped_template, safe_context)
    result = result.translate(_SWAP)
    return _unescape_protected(result)
