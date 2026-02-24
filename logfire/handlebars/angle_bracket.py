"""Angle-bracket Handlebars: full Handlebars features via <<>> syntax.

This module provides ``angle_render`` which lets you use ``<<>>`` as the
delimiter instead of ``{{}}``. This is the engine behind variable composition
(``<<variable>>`` references) — it gives ``<<>>`` syntax the full power of
Handlebars (conditionals, loops, helpers, etc.) while preserving any ``{{}}``
runtime placeholders untouched.

Algorithm (swap + protect):
  1. Topo-sort context values by their ``<<ref>>`` dependencies
  2. Resolve each value in dependency order using single-pass rendering:
     a. Protect ``{}<>`` characters in context values with HTML entities
     b. Swap ``{↔<`` and ``}↔>`` in the template (so ``<<>>`` becomes ``{{}}``)
     c. Run standard Handlebars
     d. Reverse swap
     e. Unescape the entities we introduced
  3. Render the top-level template with the fully-resolved context
"""

from __future__ import annotations

import re
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


# ---------------------------------------------------------------------------
# Reference detection for topo-sort
# ---------------------------------------------------------------------------
_ANGLE_REF = re.compile(r'<<([a-zA-Z_]\w*)>>')


def _find_refs(value: Any) -> set[str]:
    """Find <<name>> references in a string value."""
    if isinstance(value, str):
        return set(_ANGLE_REF.findall(value))
    return set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def angle_render(template: str, context: dict[str, Any]) -> str:
    """Render a template using ``<<>>`` syntax for variable composition.

    - ``<<variable>>`` references are resolved from context (recursively via topo-sort)
    - Full Handlebars features work: ``<<#if>>``, ``<<#each>>``, ``<<#unless>>``, helpers, etc.
    - ``{{runtime}}`` placeholders are preserved untouched for later rendering

    Args:
        template: The template string using ``<<>>`` delimiters.
        context: A dictionary of variable names to their values. Values that
            are strings containing ``<<ref>>`` references to other context keys
            are resolved in dependency order before the final render.

    Returns:
        The rendered string with all ``<<>>`` expressions evaluated.

    Raises:
        ValueError: If a circular reference is detected among context values.
    """
    # Build dependency graph (only for context keys that reference other context keys)
    deps: dict[str, set[str]] = {}
    for k, v in context.items():
        deps[k] = _find_refs(v) & set(context.keys())

    # Topo-sort: resolve leaf values first, then values that depend on them
    resolved: dict[str, Any] = {}
    remaining = dict(deps)

    while remaining:
        ready = [k for k, d in remaining.items() if d <= set(resolved.keys())]
        if not ready:
            raise ValueError(f'Circular reference among: {set(remaining.keys())}')
        for k in ready:
            v = context[k]
            if isinstance(v, str) and deps[k]:
                # This value has <<>> refs to other context values — render them
                resolved[k] = render_once(v, resolved)
            else:
                resolved[k] = v
            del remaining[k]

    return render_once(template, resolved)
