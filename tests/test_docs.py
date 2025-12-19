"""Test Python code examples in documentation and docstrings."""

from __future__ import annotations

import os

import pytest
from pytest_examples import CodeExample, EvalExample, find_examples

# Prevent accidental live API calls during testing
os.environ.setdefault('LOGFIRE_SEND_TO_LOGFIRE', 'false')


@pytest.mark.parametrize('example', find_examples('docs/', 'README.md'), ids=str)
async def test_documentation_examples(example: CodeExample, eval_example: EvalExample):
    """Test all Python code examples in documentation."""
    if example.prefix_settings().get('test') == 'skip':
        pytest.skip('Skipping example')

    eval_example.config.isort = True

    eval_example.config.ruff_ignore = [
        'D101',  # ignore missing docstring in public classes
        'D102',  # ignore missing docstring in public methods
        'D103',  # ignore missing docstring in public functions
    ]

    if eval_example.update_examples:
        eval_example.format(example)
    else:
        eval_example.lint_ruff(example)


@pytest.mark.parametrize('example', find_examples('logfire/'), ids=str)
def test_docstring_examples(example: CodeExample, eval_example: EvalExample):
    """Test Python code examples in source docstrings."""
    eval_example.config.ruff_ignore = [
        'D101',  # ignore missing docstring in public classes
        'D102',  # ignore missing docstring in public methods
        'D103',  # ignore missing docstring in public functions
    ]
    
    if eval_example.update_examples:
        eval_example.format(example)
    else:
        eval_example.lint_ruff(example)
