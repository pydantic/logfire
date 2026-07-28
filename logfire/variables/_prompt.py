from __future__ import annotations

import re
import warnings

PROMPT_VARIABLE_PREFIX = 'prompt__'
"""Prefix the Logfire backend uses for the managed variable that backs a prompt."""

_PROMPT_SLUG_PATTERN = re.compile(r'^[a-z0-9-]{1,100}$')
"""Valid prompt slugs, matching the identifier the Logfire backend assigns: 1-100 characters of
lowercase letters, digits, and hyphens."""


def prompt_variable_name(name: str, *, stacklevel: int = 2) -> str:
    """Translate a prompt slug into the name of the managed variable that backs it.

    Prepends the `prompt__` prefix and normalizes hyphens to underscores, matching the naming
    the Logfire backend uses for prompt-backed variables, so `support-agent` becomes
    `prompt__support_agent`. This is the one translation used by `logfire.prompt()` and
    `logfire.template_prompt()` (and intended for reuse by future integrations, e.g.
    pydantic-ai managed prompts), so the backing-variable name a prompt resolves to does
    not depend on which entry point declared it.

    The slug must match the identifier the Logfire backend assigns a prompt: 1-100 characters of
    lowercase letters, digits, and hyphens (as shown in the prompt's URL, e.g. `support-agent`).
    Anything else -- most commonly an uppercased name, or the underscored backing-variable name --
    would resolve to a *different* managed variable than the backend stores and silently fall back
    to the code default, so it raises `ValueError` instead.

    Args:
        name: The prompt slug, e.g. `support-agent`.
        stacklevel: Stack level for the accidental-prefix warning. Defaults to `2`, so a direct
            `prompt_variable_name(...)` call points the warning at its caller; `logfire.prompt()`
            and `logfire.template_prompt()` pass `3` so it points at the user's call site instead.

    Raises:
        ValueError: If `name` is not a valid prompt slug.
    """
    if name.startswith(PROMPT_VARIABLE_PREFIX):
        warnings.warn(
            f'The {PROMPT_VARIABLE_PREFIX!r} prefix is added automatically; '
            f'pass the bare prompt slug rather than {name!r}.',
            stacklevel=stacklevel,
        )
        name = name[len(PROMPT_VARIABLE_PREFIX) :]

    if not _PROMPT_SLUG_PATTERN.fullmatch(name):
        raise ValueError(
            f'Invalid prompt slug {name!r}. Prompt slugs must be 1-100 characters and contain only '
            "lowercase letters, digits, and hyphens (e.g. 'support-agent'), matching the slug "
            'Logfire assigns the prompt.'
        )

    return f'{PROMPT_VARIABLE_PREFIX}{name.replace("-", "_")}'


def prompt_slug_from_variable_name(variable_name: str) -> str:
    """Translate a prompt's backing-variable name back to its slug.

    The exact inverse of `prompt_variable_name()`: strips the `prompt__` prefix and
    normalizes underscores back to hyphens, so `prompt__support_agent` becomes
    `support-agent`. Safe because slugs cannot contain underscores — every underscore
    in a backing name came from a hyphen.

    Args:
        variable_name: The backing managed-variable name, e.g. `prompt__support_agent`.

    Raises:
        ValueError: If `variable_name` does not carry the `prompt__` prefix.
    """
    if not variable_name.startswith(PROMPT_VARIABLE_PREFIX):
        raise ValueError(
            f'{variable_name!r} is not a prompt-backed variable name; expected the {PROMPT_VARIABLE_PREFIX!r} prefix.'
        )
    return variable_name[len(PROMPT_VARIABLE_PREFIX) :].replace('_', '-')
