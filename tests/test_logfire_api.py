from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable
from unittest.mock import MagicMock

import pytest
from pydantic import __version__ as pydantic_version

from logfire._internal.utils import get_version

pydantic_pre_2_5 = get_version(pydantic_version) < get_version('2.5.0')


def logfire_dunder_all() -> set[str]:
    logfire = importlib.import_module('logfire')
    return set(logfire.__all__)


def import_logfire_api_without_logfire() -> ModuleType:
    logfire = sys.modules['logfire']
    try:
        sys.modules['logfire'] = None  # type: ignore
        sys.modules.pop('logfire_api', None)
        return importlib.import_module('logfire_api')
    finally:
        sys.modules['logfire'] = logfire


def import_logfire_api_with_logfire() -> ModuleType:
    logfire_api = importlib.import_module('logfire_api')
    return importlib.reload(logfire_api)


@pytest.mark.parametrize(
    ['logfire_api_factory', 'module_name'],
    [
        pytest.param(import_logfire_api_without_logfire, 'logfire_api.', id='without_logfire'),
        pytest.param(import_logfire_api_with_logfire, 'logfire.', id='with_logfire'),
    ],
)
def test_runtime(logfire_api_factory: Callable[[], ModuleType], module_name: str) -> None:
    logfire__all__ = logfire_dunder_all()

    logfire_api = logfire_api_factory()
    assert logfire_api is not None

    for member in dir(logfire_api):
        if member.startswith('instrument_'):
            assert member in logfire__all__, member

    assert hasattr(logfire_api, 'Logfire')
    assert module_name in str(logfire_api.Logfire())
    logfire__all__.remove('Logfire')

    assert hasattr(logfire_api, 'configure')
    logfire_api.configure(send_to_logfire=False, console=False)
    logfire__all__.remove('configure')

    assert hasattr(logfire_api, 'VERSION')
    logfire__all__.remove('VERSION')

    assert hasattr(logfire_api, 'LevelName')
    logfire__all__.remove('LevelName')

    with logfire_api.span('test span') as span:
        assert isinstance(span, logfire_api.LogfireSpan)
        span.set_attribute('foo', 'bar')
    logfire__all__.remove('LogfireSpan')
    logfire__all__.remove('span')

    assert hasattr(logfire_api, 'log')
    logfire_api.log('info', 'test log')
    logfire__all__.remove('log')

    for log_method in ['trace', 'debug', 'info', 'notice', 'warn', 'warning', 'error', 'exception', 'fatal']:
        assert hasattr(logfire_api, log_method)
        getattr(logfire_api, log_method)('test log')
        logfire__all__.remove(log_method)

    assert hasattr(logfire_api, 'with_settings')
    assert isinstance(logfire_api.with_settings(), logfire_api.Logfire)
    logfire__all__.remove('with_settings')

    assert hasattr(logfire_api, 'with_tags')
    logfire_api.with_tags('test tag')
    logfire__all__.remove('with_tags')

    assert hasattr(logfire_api, 'force_flush')
    logfire_api.force_flush()
    logfire__all__.remove('force_flush')

    assert hasattr(logfire_api, 'no_auto_trace')
    logfire_api.no_auto_trace(lambda: None)  # pragma: no branch
    logfire__all__.remove('no_auto_trace')

    assert hasattr(logfire_api, 'add_non_user_code_prefix')
    logfire_api.add_non_user_code_prefix('/foo/bar')
    logfire__all__.remove('add_non_user_code_prefix')

    assert hasattr(logfire_api, 'suppress_instrumentation')
    with logfire_api.suppress_instrumentation():
        ...
    logfire__all__.remove('suppress_instrumentation')

    assert hasattr(logfire_api, 'suppress_scopes')
    logfire_api.suppress_scopes()
    logfire__all__.remove('suppress_scopes')

    assert hasattr(logfire_api, 'ConsoleOptions')
    logfire_api.ConsoleOptions(colors='auto')
    logfire__all__.remove('ConsoleOptions')

    assert hasattr(logfire_api, 'PydanticPlugin')
    logfire_api.PydanticPlugin()
    logfire__all__.remove('PydanticPlugin')

    assert hasattr(logfire_api, 'ScrubMatch')
    logfire_api.ScrubMatch(path='test', value='test', pattern_match='test')
    logfire__all__.remove('ScrubMatch')

    assert hasattr(logfire_api, 'log_slow_async_callbacks')
    # NOTE: We don't call the log_slow_async_callbacks, to not give side effect to the test suite.
    logfire__all__.remove('log_slow_async_callbacks')

    assert hasattr(logfire_api, 'install_auto_tracing')
    logfire_api.install_auto_tracing(modules=['all'], min_duration=0)
    logfire__all__.remove('install_auto_tracing')

    assert hasattr(logfire_api, 'instrument')

    @logfire_api.instrument()
    def func() -> None: ...

    func()
    logfire__all__.remove('instrument')

    assert hasattr(logfire_api, 'instrument_aws_lambda'), 'instrument_aws_lambda'
    logfire_api.instrument_aws_lambda(lambda_handler=MagicMock())
    logfire__all__.remove('instrument_aws_lambda')

    assert hasattr(logfire_api, 'instrument_asgi'), 'instrument_asgi'
    assert getattr(logfire_api, 'instrument_asgi')(app=MagicMock()) is not None
    logfire__all__.remove('instrument_asgi')

    assert hasattr(logfire_api, 'instrument_wsgi'), 'instrument_wsgi'
    assert getattr(logfire_api, 'instrument_wsgi')(app=MagicMock()) is not None
    logfire__all__.remove('instrument_wsgi')

    for member in [m for m in ('instrument_flask', 'instrument_fastapi', 'instrument_starlette')]:
        assert hasattr(logfire_api, member), member
        getattr(logfire_api, member)(app=MagicMock())
        logfire__all__.remove(member)

    for member in [m for m in ('instrument_openai', 'instrument_anthropic')]:
        assert hasattr(logfire_api, member), member
        with getattr(logfire_api, member)():
            ...
        logfire__all__.remove(member)

    assert hasattr(logfire_api, 'instrument_openai_agents')
    if sys.version_info >= (3, 9):
        logfire_api.instrument_openai_agents()
    logfire__all__.remove('instrument_openai_agents')

    assert hasattr(logfire_api, 'instrument_pydantic_ai')
    if sys.version_info >= (3, 9) and not pydantic_pre_2_5:
        logfire_api.instrument_pydantic_ai()
    logfire__all__.remove('instrument_pydantic_ai')

    assert hasattr(logfire_api, 'instrument_mcp')
    if sys.version_info >= (3, 10) and not pydantic_pre_2_5:
        logfire_api.instrument_mcp()
    logfire__all__.remove('instrument_mcp')

    for member in [m for m in logfire__all__ if m.startswith('instrument_')]:
        assert hasattr(logfire_api, member), member
        if not (pydantic_pre_2_5 and member == 'instrument_pydantic'):
            # skip pydantic instrumentation (which uses the plugin) for versions prior to v2.5
            getattr(logfire_api, member)()
        # just remove the member unconditionally to pass future asserts
        logfire__all__.remove(member)

    assert hasattr(logfire_api, 'shutdown')
    logfire_api.shutdown()
    logfire__all__.remove('shutdown')

    assert hasattr(logfire_api, 'AutoTraceModule')
    logfire_api.AutoTraceModule(name='test', filename='test')
    logfire__all__.remove('AutoTraceModule')

    assert hasattr(logfire_api, 'LogfireLoggingHandler')
    logfire_api.LogfireLoggingHandler()
    logfire__all__.remove('LogfireLoggingHandler')

    assert hasattr(logfire_api, 'loguru_handler')
    logfire_api.loguru_handler()
    logfire__all__.remove('loguru_handler')

    assert hasattr(logfire_api, 'StructlogProcessor')
    logfire_api.StructlogProcessor()
    logfire__all__.remove('StructlogProcessor')

    assert hasattr(logfire_api, 'SamplingOptions')
    logfire_api.SamplingOptions()
    logfire__all__.remove('SamplingOptions')

    assert hasattr(logfire_api, 'CodeSource')
    logfire_api.CodeSource(repository='https://github.com/pydantic/logfire', revision='main', root_path='test')
    logfire__all__.remove('CodeSource')

    assert hasattr(logfire_api, 'ScrubbingOptions')
    logfire_api.ScrubbingOptions()
    logfire__all__.remove('ScrubbingOptions')

    assert hasattr(logfire_api, 'AdvancedOptions')
    logfire_api.AdvancedOptions()
    logfire__all__.remove('AdvancedOptions')

    assert hasattr(logfire_api, 'MetricsOptions')
    logfire_api.MetricsOptions()
    logfire__all__.remove('MetricsOptions')

    assert hasattr(logfire_api, 'logfire_info')
    logfire_api.logfire_info()
    logfire__all__.remove('logfire_info')

    # If it's not empty, it means that some of the __all__ members are not tested.
    assert logfire__all__ == set(), logfire__all__


@pytest.mark.skipif(sys.version_info < (3, 11), reason='We only need this test for a single Python version.')
def test_match_version_on_pyproject() -> None:
    import tomllib

    logfire_pyproject = (Path(__file__).parent.parent / 'pyproject.toml').read_text()
    logfire_api_pyproject = (Path(__file__).parent.parent / 'logfire-api' / 'pyproject.toml').read_text()

    logfire_pyproject_content = tomllib.loads(logfire_pyproject)
    logfire_api_pyproject_content = tomllib.loads(logfire_api_pyproject)

    assert logfire_pyproject_content['project']['version'] == logfire_api_pyproject_content['project']['version']


def test_override_init_pyi() -> None:  # pragma: no cover
    """The logic here is:

    1. If `span: Incomplete` is present, it means we need to regenerate the `DEFAULT_LOGFIRE_INSTANCE` logic.
    2. If the `span: Incomplete` is present, but we have `Incomplete` in the file, it means we need to update to a
        `DEFAULT_LOGFIRE_INSTANCE` logic.
    3. If none of the above is present, we skip the test.
    """
    incomplete = ': Incomplete'
    len_incomplete = len(incomplete)

    init_pyi = (Path(__file__).parent.parent / 'logfire-api' / 'logfire_api' / '__init__.pyi').read_text()
    lines = init_pyi.splitlines()

    try:
        span_index = lines.index('span: Incomplete')
    except ValueError:
        for i, line in enumerate(lines.copy()):
            if line.endswith(incomplete):
                prefix = line[: len(line) - len_incomplete]
                lines[i] = f'{prefix} = DEFAULT_LOGFIRE_INSTANCE.{prefix}'
    else:
        default_logfire_instance = 'DEFAULT_LOGFIRE_INSTANCE'

        new_end_lines: list[str] = [f'{default_logfire_instance} = Logfire()']

        for line in lines[span_index:]:
            if line.endswith(incomplete):
                prefix = line[: len(line) - len_incomplete]
                new_end_lines.append(f'{prefix} = {default_logfire_instance}.{prefix}')
            else:
                new_end_lines.append(line)
        lines.remove('from _typeshed import Incomplete')
        lines[span_index - 1 :] = new_end_lines

    new_init_pyi = '\n'.join(lines) + '\n'
    if new_init_pyi == init_pyi:
        pytest.skip('No changes were made to the __init__.pyi file.')
    (Path(__file__).parent.parent / 'logfire-api' / 'logfire_api' / '__init__.pyi').write_text(new_init_pyi)
    pytest.fail('The __init__.pyi file was updated.')
