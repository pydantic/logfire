"""Tests that enforce the single-source-of-truth for the agent setup prompt (issue #2202).

The canonical prompt lives in docs/agent-setup-prompt.txt and is included into both
docs/index.md and docs/first-trace.md via a {{ agent_setup_prompt() }} substitution
in the docs build plugin. These tests assert that structure is intact so that neither
page can silently diverge from the canonical file.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent
PROMPT_FILE = REPO_ROOT / 'docs' / 'agent-setup-prompt.txt'
INDEX_MD = REPO_ROOT / 'docs' / 'index.md'
FIRST_TRACE_MD = REPO_ROOT / 'docs' / 'first-trace.md'

PLACEHOLDER = '{{ agent_setup_prompt() }}'


def module_with_attributes(name: str, **attributes: object) -> ModuleType:
    module = ModuleType(name)
    for attribute_name, value in attributes.items():
        setattr(module, attribute_name, value)
    return module


def load_agent_setup_prompt() -> Callable[[str, object], str]:
    mkdocs = module_with_attributes('mkdocs', __path__=[])
    mkdocs_structure = module_with_attributes('mkdocs.structure', __path__=[])
    mkdocs_modules = {
        'mkdocs': mkdocs,
        'mkdocs.config': module_with_attributes('mkdocs.config', Config=object),
        'mkdocs.structure': mkdocs_structure,
        'mkdocs.structure.files': module_with_attributes('mkdocs.structure.files', Files=object),
        'mkdocs.structure.pages': module_with_attributes('mkdocs.structure.pages', Page=object),
    }
    spec = importlib.util.spec_from_file_location('test_docs_plugins_main', REPO_ROOT / 'docs' / 'plugins' / 'main.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, mkdocs_modules):
        spec.loader.exec_module(module)
    return cast('Callable[[str, object], str]', module.agent_setup_prompt)


agent_setup_prompt = load_agent_setup_prompt()


def page_with_src_uri(src_uri: str) -> object:
    return SimpleNamespace(file=SimpleNamespace(src_uri=src_uri))


def test_canonical_prompt_file_exists_and_is_nonempty() -> None:
    """docs/agent-setup-prompt.txt is the single source of truth for the agent setup
    prompt. It must exist and contain content so that the docs build substitution has
    something to inject."""
    assert PROMPT_FILE.exists(), f'{PROMPT_FILE} does not exist'
    content = PROMPT_FILE.read_text(encoding='utf-8').strip()
    assert content, f'{PROMPT_FILE} is empty'


def test_index_md_uses_substitution_not_hardcoded_copy() -> None:
    """docs/index.md must use the {{ agent_setup_prompt() }} substitution inside its
    <AgentSetup> block rather than a hardcoded copy of the prompt. This prevents the
    two sources from drifting: the build plugin expands the placeholder at render time."""
    content = INDEX_MD.read_text(encoding='utf-8')
    assert PLACEHOLDER in content, (
        f'{INDEX_MD} does not contain the {PLACEHOLDER!r} substitution. '
        'Add it inside the <AgentSetup> block so the canonical prompt is rendered there.'
    )


def test_first_trace_md_uses_substitution_not_hardcoded_copy() -> None:
    """docs/first-trace.md must use the {{ agent_setup_prompt() }} substitution inside
    its <CopyPrompt> block rather than a hardcoded copy of the prompt. This prevents
    the two sources from drifting: the build plugin expands the placeholder at render time."""
    content = FIRST_TRACE_MD.read_text(encoding='utf-8')
    assert PLACEHOLDER in content, (
        f'{FIRST_TRACE_MD} does not contain the {PLACEHOLDER!r} substitution. '
        'Add it inside the <CopyPrompt> block so the canonical prompt is rendered there.'
    )


def test_prompt_file_contains_no_hardcoded_copies_in_md_files() -> None:
    """Sanity check: neither docs page should contain the raw first line of the canonical
    prompt verbatim, which would indicate someone pasted a copy instead of using the
    substitution. (The substitution placeholder itself is tested by the other tests.)"""
    prompt_first_line = PROMPT_FILE.read_text(encoding='utf-8').splitlines()[0].strip()
    for md_file in (INDEX_MD, FIRST_TRACE_MD):
        content = md_file.read_text(encoding='utf-8')
        assert prompt_first_line not in content, (
            f'{md_file} appears to contain a hardcoded copy of the agent setup prompt '
            f'(found the first line verbatim: {prompt_first_line!r}). '
            f'Use the {PLACEHOLDER!r} substitution instead.'
        )


@pytest.mark.parametrize('src_uri', ['index.md', 'first-trace.md'])
def test_agent_setup_prompt_expands_canonical_prompt(src_uri: str) -> None:
    markdown = f'before\n{PLACEHOLDER}\nafter'
    canonical_prompt = PROMPT_FILE.read_text(encoding='utf-8')

    rendered_markdown = agent_setup_prompt(markdown, page_with_src_uri(src_uri))

    assert rendered_markdown == markdown.replace(PLACEHOLDER, canonical_prompt)
