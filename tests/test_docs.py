"""Test Python code examples in documentation and docstrings."""

import gc
import os

import pytest
from pytest_examples import CodeExample, EvalExample, find_examples

# Prevent accidental live API calls during testing
os.environ.setdefault('LOGFIRE_SEND_TO_LOGFIRE', 'false')

ruff_ignore = [
    'D101',  # ignore missing docstring in public classes
    'D102',  # ignore missing docstring in public methods
    'D103',  # ignore missing docstring in public functions
]

SKIP_RUN_TAGS = ['skip', 'skip-run']
"""Tags to skip running the example with pytest-examples."""

SKIP_LINT_TAGS = ['skip', 'skip-lint']
"""Tags to skip linting the example with pytest-examples."""


def set_eval_config(eval_example: EvalExample):
    """Set the evaluation configuration."""
    eval_example.set_config(
        line_length=120,
        quotes='single',
        isort=True,
        ruff_ignore=ruff_ignore,
        target_version='py39',
    )


def test_formatting(eval_example: EvalExample):
    """Ensure examples in documentation are formatted correctly."""
    examples = find_examples('docs/', 'README.md')
    # Filter out skipped examples
    examples = [ex for ex in examples if not any(ex.prefix_settings().get(key) == 'true' for key in SKIP_LINT_TAGS)]

    set_eval_config(eval_example)

    for example in examples:
        if eval_example.update_examples:  # pragma: no cover
            eval_example.format(example)
        else:
            eval_example.lint_ruff(example)


def _get_runnable_examples():
    """Get examples that should be run, filtering out skipped ones."""
    examples = find_examples('logfire/', 'docs/', 'README.md')
    return [ex for ex in examples if not any(ex.prefix_settings().get(key) == 'true' for key in SKIP_RUN_TAGS)]


@pytest.mark.parametrize('example', _get_runnable_examples(), ids=str)
@pytest.mark.timeout(3)
def test_runnable(example: CodeExample, eval_example: EvalExample):
    """Ensure examples in documentation are runnable."""
    set_eval_config(eval_example)

    if eval_example.update_examples:  # pragma: no cover
        eval_example.run_print_update(example)
    else:
        eval_example.run_print_check(example)

    gc.collect()
