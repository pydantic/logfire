"""Reference-syntax Handlebars: low-level primitive for `@{}@` rendering.

This module provides `render_once`, a thin wrapper that runs
`pydantic_handlebars.render` with `open_delim='@{'` / `close_delim='}@'`.
Used as the engine behind variable composition — any `{{...}}` runtime
placeholders in the template survive untouched (they're plain content
under the custom delimiters) for a later rendering pass.

This module used to perform a sentinel-protect + regex-translate dance
to delegate to a stock-`{{...}}` Handlebars renderer; that workaround
was replaced by native custom-delimiter support in
``pydantic-handlebars >= 0.2``.
"""

from __future__ import annotations

from typing import Any

from logfire.variables._handlebars import get_environment


def render_once(template: str, context: dict[str, Any]) -> str:
    r"""Single-pass `@{...}@` Handlebars render.

    `{{...}}` runtime placeholders in *template* are not touched — they
    are plain content under the configured delimiters. The escape
    sequence `\@{` produces a literal `@{` in the output.
    """
    return get_environment().render(template, context)
