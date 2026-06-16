from __future__ import annotations

import warnings

PROMPT_VARIABLE_PREFIX = 'prompt__'
"""Prefix the Logfire backend uses for the managed variable that backs a prompt."""


def prompt_variable_name(name: str) -> str:
    """Translate a prompt name into the name of the managed variable that backs it.

    Prepends the `prompt__` prefix and normalizes hyphens to underscores, matching the naming
    the Logfire backend uses for prompt-backed variables, so `support-agent` becomes
    `prompt__support_agent`. This is the one translation shared by `logfire.prompt()`,
    `logfire.template_prompt()`, and the pydantic-ai `ManagedPrompt` capability, so the
    backing-variable name a prompt resolves to does not depend on which entry point declared it.

    Raises `ValueError` if the resulting variable name is not a valid Python identifier.
    """
    if name.startswith(PROMPT_VARIABLE_PREFIX):
        warnings.warn(
            f'The {PROMPT_VARIABLE_PREFIX!r} prefix is added automatically; '
            f'pass the bare prompt name rather than {name!r}.',
            stacklevel=3,
        )
        name = name[len(PROMPT_VARIABLE_PREFIX) :]

    variable_name = f'{PROMPT_VARIABLE_PREFIX}{name.replace("-", "_")}'
    if not variable_name.isidentifier():
        raise ValueError(
            f'Prompt name {name!r} produces an invalid variable name {variable_name!r}; '
            'prompt names may only contain letters, digits, hyphens, and underscores.'
        )
    return variable_name
