"""Test Python code examples in documentation and docstrings."""

import os

import pytest
from pytest_examples import CodeExample, EvalExample, find_examples

import logfire

# Prevent accidental live API calls during testing
os.environ.setdefault('LOGFIRE_SEND_TO_LOGFIRE', 'false')

ruff_ignore = [
    'D101',  # ignore missing docstring in public classes
    'D102',  # ignore missing docstring in public methods
    'D103',  # ignore missing docstring in public functions
]


# Override the autouse fixtures from conftest.py to prevent them from
# interfering with doc examples. Doc examples call their own logfire.configure()
# and we don't want them to pollute the test exporter state.
@pytest.fixture(autouse=True)
def config():
    """Override the conftest config fixture - doc examples configure themselves."""
    logfire.configure(send_to_logfire=False, console=False)


def get_skip_reason(example: CodeExample):
    """Get the reason for skipping the example."""
    return example.prefix_settings().get('skip-reason')


def set_eval_config(eval_example: EvalExample):
    """Set the evaluation configuration."""
    eval_example.set_config(
        line_length=120,
        quotes='single',
        isort=True,
        ruff_ignore=ruff_ignore,
        target_version='py39',
    )


@pytest.mark.parametrize('example', find_examples('docs/', 'README.md'), ids=str)
@pytest.mark.timeout(3)
def test_formatting(example: CodeExample, eval_example: EvalExample):
    """Ensure examples in documentation are formatted correctly."""
    if any(example.prefix_settings().get(key) == 'true' for key in ['skip', 'skip-lint']):
        pytest.skip(get_skip_reason(example) or 'Skipping example')

    set_eval_config(eval_example)

    if eval_example.update_examples:  # pragma: no cover
        eval_example.format(example)
    else:
        eval_example.lint_ruff(example)


@pytest.mark.parametrize('example', find_examples('logfire/', 'docs/', 'README.md'), ids=str)
@pytest.mark.timeout(3)
def test_runnable(example: CodeExample, eval_example: EvalExample):
    """Ensure examples in documentation are runnable."""

    if any(example.prefix_settings().get(key) == 'true' for key in ['skip', 'skip-run']):
        pytest.skip(get_skip_reason(example) or 'Skipping example')

    set_eval_config(eval_example)

    if eval_example.update_examples:  # pragma: no cover
        eval_example.run_print_update(example)
    else:
        eval_example.run_print_check(example)
