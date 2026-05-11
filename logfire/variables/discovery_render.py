"""POC: render-based dependency discovery for @{}@ references.

Alternative to the regex-based ``find_references`` in ``composition.py``. Instead
of scraping the template text with regexes, this runs the Handlebars renderer
itself against a tracking context that records every top-level lookup. Block
helpers (``if``/``unless``/``each``/``with``) are overridden to render BOTH
their primary and inverse branches, so references hidden in either branch are
still discovered.

Goals: prove that this approach can discover everything the regex finds, plus
cases the regex misses such as dotted paths inside block headers
(``@{#if user.active}@``).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic_handlebars import HandlebarsEnvironment
from pydantic_handlebars._compiler import HelperOptions

# Names that appear in @{...}@ syntax but are Handlebars built-ins, not variables.
_HBS_KEYWORDS = frozenset({'else', 'this'})

# Same protect/rewrite logic as reference_syntax.render_once, but without rendering.
_REFERENCE_TAG = re.compile(r'(?<!\\)@\{(.*?)\}@')
_ESCAPED_REFERENCE_START = r'\@{'


class _TrackingSentinel(list[Any]):
    """List-of-one-element so it is truthy AND iterable (for #each).

    Subclasses list so ``isinstance(value, list)`` checks in the renderer treat
    it as iterable. Holds one fake item so #each renders its body exactly once.
    """

    def __init__(self, name: str) -> None:
        super().__init__([_TrackingChild(name)])
        self._name = name


class _TrackingChild(dict[str, Any]):
    """Returned for dotted-path traversal so e.g. ``user.active`` still resolves.

    Returning a dict subclass lets ``_get_property`` continue walking the path
    via ``.get(...)`` without raising. We don't care about the result of nested
    access — we already recorded the top-level name.
    """

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name

    def get(self, key: str, default: Any = None) -> Any:
        return _TrackingChild(self._name)

    def __getitem__(self, key: str) -> Any:
        return _TrackingChild(self._name)


class _TrackingContext(dict[str, Any]):
    """Dict subclass that records every top-level key lookup."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []
        self._seen_set: set[str] = set()

    def _record(self, name: str) -> None:
        if name in _HBS_KEYWORDS:
            return
        if name in self._seen_set:
            return
        self._seen_set.add(name)
        self.seen.append(name)

    def get(self, key: str, default: Any = None) -> Any:
        self._record(key)
        return _TrackingSentinel(key)

    def __getitem__(self, key: str) -> Any:
        self._record(key)
        return _TrackingSentinel(key)


# --- Block helpers that render BOTH branches so refs in either are discovered.


def _both_branches_if(context: Any, *args: Any, options: HelperOptions) -> str:
    fn_part = options.fn(context)
    inverse_part = options.inverse(context)
    return fn_part + inverse_part


def _both_branches_each(context: Any, *args: Any, options: HelperOptions) -> str:
    # Pass the parent context (the top-level tracker) as the iterated item so
    # that inner `{{x}}` references resolve through our tracker rather than a
    # child scope. block_params include `context` so `as |item|` still works.
    body = options.fn(context, data={'index': 0, 'first': True, 'last': True}, block_params=[context, 0])
    inverse_part = options.inverse(context)
    return body + inverse_part


def _both_branches_with(context: Any, *args: Any, options: HelperOptions) -> str:
    # Same idea — keep the parent tracker as the context so inner refs are
    # recorded at the top level.
    body = options.fn(context)
    inverse_part = options.inverse(context)
    return body + inverse_part


def _build_env() -> HandlebarsEnvironment:
    env = HandlebarsEnvironment()
    env.register_helper('if', _both_branches_if)
    env.register_helper('unless', _both_branches_if)  # symmetric: same both-branch behavior
    env.register_helper('each', _both_branches_each)
    env.register_helper('with', _both_branches_with)
    return env


_ENV = _build_env()


def _rewrite_to_handlebars(template: str) -> str:
    """Same logic as reference_syntax.render_once, minus rendering."""
    sentinel_left = '\x00pf-left-rt\x00'
    sentinel_right = '\x00pf-right-rt\x00'
    sentinel_escaped = '\x00pf-esc-ref\x00'
    protected = (
        template.replace(_ESCAPED_REFERENCE_START, sentinel_escaped)
        .replace('{{', sentinel_left)
        .replace('}}', sentinel_right)
    )
    return _REFERENCE_TAG.sub(r'{{\1}}', protected)


def find_references_via_render(serialized_value: str) -> list[str]:
    """Discover top-level variable references by running a tracking render pass."""
    seen: list[str] = []
    seen_set: set[str] = set()

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            handlebars_template = _rewrite_to_handlebars(value)
            context = _TrackingContext()
            try:
                # NB: bypass HandlebarsEnvironment.render — it calls
                # to_jsonable_python(ctx) which flattens our subclass to a
                # plain dict and discards the side-effecting .get.
                fn = _ENV._compile_fn(handlebars_template)  # pyright: ignore[reportPrivateUsage]
                fn(context)
            except Exception:
                # Parse errors, unknown-helper runtime errors, etc. — for the
                # POC we just record whatever we got before bailing.
                pass
            for name in context.seen:
                if name not in seen_set:
                    seen_set.add(name)
                    seen.append(name)
        elif isinstance(value, dict):
            for v in value.values():  # pyright: ignore[reportUnknownVariableType]
                _walk(v)
        elif isinstance(value, list):
            for v in value:  # pyright: ignore[reportUnknownVariableType]
                _walk(v)

    try:
        decoded = json.loads(serialized_value)
    except (json.JSONDecodeError, TypeError):
        return []

    _walk(decoded)
    return seen
