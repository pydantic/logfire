"""Test Python code examples in documentation and docstrings."""

from __future__ import annotations

from asyncio import timeout
import os

import pytest
from pytest_examples import CodeExample, EvalExample, find_examples

# Prevent accidental live API calls during testing
os.environ.setdefault('LOGFIRE_SEND_TO_LOGFIRE', 'false')


@pytest.mark.parametrize('example', find_examples('docs/', 'README.md'), ids=str)
async def test_documentation_examples(example: CodeExample, eval_example: EvalExample):
    """Test all Python code examples in documentation."""
    eval_example.config.ruff_ignore = ['D103']  # ignore missing docstring in public functions
    eval_example.config.ruff_config
    eval_example.lint(example)
    if eval_example.update_examples:
        eval_example.format(example)
    # if eval_example.update_examples:
    # eval_example.format(example)
    # eval_example.run_print_update
    # eval_example.run_print_update(example)
    # else:
    # eval_example.lint(example)
    # eval_example.run_print_check(example)


@pytest.mark.parametrize('example', find_examples('logfire/'), ids=str)
def test_docstring_examples(example: CodeExample, eval_example: EvalExample):
    """Test Python code examples in source docstrings."""
    eval_example.lint(example)
    eval_example.run(example)
