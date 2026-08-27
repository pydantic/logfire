"""Test Python code examples in documentation and docstrings."""

import gc
import os
import re
from pathlib import Path

import pydantic
import pytest
from pytest_examples import CodeExample, EvalExample, find_examples

from logfire._internal.utils import get_version

# Prevent accidental live API calls during testing
os.environ.setdefault('LOGFIRE_SEND_TO_LOGFIRE', 'false')

ruff_ignore = [
    'D101',  # ignore missing docstring in public classes
    'D102',  # ignore missing docstring in public methods
    'D103',  # ignore missing docstring in public functions
    # Rules newly enabled by default in ruff 0.16 that docs examples trip.
    # Examples favour brevity and realism over lint strictness.
    'B017',  # pytest.raises(Exception)
    'B018',  # useless expression
    'BLE001',  # blind except Exception
    'DTZ011',  # date.today() without timezone
    'PIE790',  # unnecessary pass/ellipsis
    'SIM117',  # nested with statements
    'SIM118',  # key in dict.keys()
    'TRY002',  # raise plain Exception
    'UP035',  # deprecated import (e.g. typing.List)
]

SKIP_RUN_TAGS = ['skip', 'skip-run']
"""Tags to skip running the example with pytest-examples."""

SKIP_LINT_TAGS = ['skip', 'skip-lint']
"""Tags to skip linting the example with pytest-examples."""

COLLECTION_INTERVAL_PATTERN = re.compile(r'\bcollection_interval:\s*["\']?(\d+(?:\.\d+)?)(ms|s|m)\b')
MILLISECOND_METRIC_INTERVAL_PATTERNS = (
    re.compile(r'\botel_interval_milliseconds\s*=\s*(\d+)\b'),
    re.compile(r'\bOTEL_METRICS?_EXPORT(?:ER)?_INTERVAL(?:_MILLIS)?=(\d+)\b'),
)


def set_eval_config(eval_example: EvalExample):
    """Set the evaluation configuration."""
    eval_example.set_config(
        line_length=120,
        quotes='single',
        isort=True,
        ruff_ignore=ruff_ignore,
        target_version='py310',
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


def test_documented_metric_intervals_are_at_least_one_minute():
    """Prevent examples from accidentally recommending high-volume metric intervals."""
    short_intervals: list[str] = []

    for path in Path('docs').rglob('*.md'):
        source = path.read_text()
        matches_with_seconds = [
            (
                match,
                float(match.group(1)) * {'ms': 0.001, 's': 1, 'm': 60}[match.group(2)],
            )
            for match in COLLECTION_INTERVAL_PATTERN.finditer(source)
        ]
        for pattern in MILLISECOND_METRIC_INTERVAL_PATTERNS:
            matches_with_seconds.extend((match, int(match.group(1)) / 1000) for match in pattern.finditer(source))

        for match, seconds in matches_with_seconds:
            if seconds < 60:
                line_number = source.count('\n', 0, match.start()) + 1
                short_intervals.append(f'{path}:{line_number}: {match.group(0)}')

    assert not short_intervals, 'Metric examples must use intervals of at least 60 seconds:\n' + '\n'.join(
        short_intervals
    )


def _get_runnable_examples():
    """Get examples that should be run, filtering out skipped ones."""
    examples = find_examples('logfire/', 'docs/', 'README.md')
    return [
        ex
        for ex in examples
        if '.agents' not in ex.path.parts and not any(ex.prefix_settings().get(key) == 'true' for key in SKIP_RUN_TAGS)
    ]


def test_skill_examples_formatting(eval_example: EvalExample):
    """Ensure skill examples are formatted, without running instrumentation snippets."""
    examples = find_examples('logfire/.agents')
    examples = [ex for ex in examples if not any(ex.prefix_settings().get(key) == 'true' for key in SKIP_LINT_TAGS)]

    eval_example.set_config(
        line_length=120,
        quotes='either',
        isort=False,
        ruff_ignore=[*ruff_ignore, 'F821', 'I001', 'Q'],
        target_version='py310',
    )

    for example in examples:
        if eval_example.update_examples:  # pragma: no cover
            eval_example.format(example)
        else:
            eval_example.lint_ruff(example)


@pytest.mark.parametrize('example', _get_runnable_examples(), ids=str)
@pytest.mark.timeout(10)
def test_runnable(example: CodeExample, eval_example: EvalExample):
    """Ensure examples in documentation are runnable."""
    if 'from fastapi' in example.source and get_version(pydantic.__version__) < get_version('2.7.0'):
        pytest.skip('FastAPI requires pydantic>=2.7')

    set_eval_config(eval_example)

    if eval_example.update_examples:  # pragma: no cover
        eval_example.run_print_update(example)
    else:
        eval_example.run_print_check(example)

    gc.collect()
