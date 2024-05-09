import pkgutil
from types import ModuleType
from typing import Iterator, cast

import openai
import pytest
from fastapi import FastAPI
from opentelemetry.metrics import CallbackOptions, Observation

import logfire
import logfire_noop
import logfire_noop.testing
from logfire.testing import CaptureLogfire

logfire_modules = set([modname for _, modname, _ in pkgutil.iter_modules(logfire.__path__)])
# Remove the modules that are not part of the public API, and the CLI.
logfire_modules.difference_update({'__main__', 'cli', '_internal'})
# TODO(Marcelo): We should actually match those as well.
logfire_modules.difference_update({'integrations'})

logfire_noop_modules = set([modname for _, modname, _ in pkgutil.iter_modules(logfire_noop.__path__)])


def test_match_public_modules() -> None:
    """Test that the public modules in `logfire` are the same as in `logfire_noop`."""
    assert logfire_modules == logfire_noop_modules


def test_dunder_all_match() -> None:
    """Test that the `__all__` in `logfire` and `logfire_noop` match."""
    assert logfire.__all__ == logfire_noop.__all__


# TODO: We need to create a visitor that checks:
# - [ ] The functions signatures, and docstring match.
# - [ ] The functions and classes are the same in both modules.
# - [ ] The `logfire_noop` package needs to be updated when the docstring is updated in `logfire`.
# - [ ] The `logfire_noop` package needs to be updated when the function signature is updated in `logfire`.


@pytest.mark.parametrize('module', [logfire, logfire_noop])
def test_noop_behavior(capfire: CaptureLogfire, module: ModuleType) -> None:
    """Test that the `logfire_noop` package behaves as expected."""

    obj = cast(logfire.Logfire, module.Logfire())

    with obj.span('span') as span:
        span.set_attribute('key', 'value')
        span.set_attributes({'key': 'value', 'key2': 'value2'})
        span.is_recording()
        span.tags

    @obj.instrument('name')
    def func() -> None: ...

    obj.force_flush()
    obj.log_slow_async_callbacks()
    # obj.install_auto_tracing()
    obj.instrument_fastapi(app=FastAPI())
    obj.instrument_openai(openai.Client())
    obj.instrument_asyncpg()
    obj.instrument_psycopg()
    obj.shutdown()
    obj = obj.with_tags('tag1', 'tag2')
    obj = obj.with_settings(custom_scope_suffix='suffix')

    # Logging
    obj.log(level='info', msg_template='message')
    obj.trace('message')
    obj.debug('message')
    obj.info('message')
    obj.notice('message')
    obj.warn('message')
    obj.error('message')
    obj.fatal('message')
    obj.exception('message')

    # Metrics
    counter = obj.metric_counter(name='metric')
    counter.add(1)

    histogram = obj.metric_histogram(name='metric')
    histogram.record(1)

    up_down_counter = obj.metric_up_down_counter(name='metric')
    up_down_counter.add(1)

    gauge = obj.metric_gauge(name='metric')
    gauge.set(1)

    def cpu_usage_callback(options: CallbackOptions) -> Iterator[Observation]:
        yield Observation(value=0.5)

    obj.metric_counter_callback(name='metric', callbacks=[cpu_usage_callback])
    obj.metric_gauge_callback(name='metric', callbacks=[cpu_usage_callback])
    obj.metric_up_down_counter_callback(name='metric', callbacks=[cpu_usage_callback])
