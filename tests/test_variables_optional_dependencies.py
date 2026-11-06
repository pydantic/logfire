from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('missing', [('pydantic',), ('pydantic_handlebars',), ('pydantic', 'pydantic_handlebars')])
def test_variables_config_import_without_dependencies(missing: tuple[str, ...], tmp_path: Path) -> None:
    code = f"""
import socket
import sys

def no_network(*args, **kwargs):
    raise AssertionError('Network access is not allowed')

socket.socket.connect = no_network
for name in {missing!r}:
    sys.modules[name] = None

import logfire
import logfire.variables
from logfire.variables import VariablesConfig

assert VariablesConfig.__name__ == 'VariablesConfig'
for use in (
    lambda: VariablesConfig(variables={{}}),
    lambda: VariablesConfig.model_validate({{'variables': {{}}}}),
    lambda: logfire.var('test', default=1),
):
    try:
        use()
    except ImportError as error:
        assert 'logfire[variables]' in str(error), str(error)
    else:
        raise AssertionError('Using managed variables must require the extra')

try:
    from logfire.variables import Variable
except ImportError as error:
    assert 'logfire[variables]' in str(error)
else:
    raise AssertionError('Other managed-variable declarations still require the extra')

for name in {missing!r}:
    del sys.modules[name]

from logfire.variables.config import VariablesConfig as RealVariablesConfig
from logfire.variables import VariablesConfig as ImportedVariablesConfig

assert ImportedVariablesConfig is RealVariablesConfig
assert isinstance(VariablesConfig(variables={{}}), RealVariablesConfig)
assert isinstance(VariablesConfig.model_validate({{'variables': {{}}}}), RealVariablesConfig)
"""
    result = subprocess.run(
        [sys.executable, '-I', '-c', code],
        capture_output=True,
        text=True,
        env={
            **{key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'PATH') if key in os.environ},
            'HOME': str(tmp_path),
            'USERPROFILE': str(tmp_path),
            'LOGFIRE_SEND_TO_LOGFIRE': 'false',
        },
    )
    assert result.returncode == 0, result.stderr


def test_variables_config_with_dependencies() -> None:
    from logfire.variables import VariablesConfig
    from logfire.variables.config import VariablesConfig as RealVariablesConfig

    assert VariablesConfig is RealVariablesConfig
    config = VariablesConfig(variables={})
    assert config.model_dump() == {'variables': {}}
    assert VariablesConfig.model_validate({'variables': {}}) == config
    assert isinstance(config, VariablesConfig)
    assert issubclass(RealVariablesConfig, VariablesConfig)


def test_deferred_variables_config_dependency_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    import logfire.variables
    from logfire.variables.config import VariablesConfig as RealVariablesConfig

    config = RealVariablesConfig(variables={})
    with monkeypatch.context() as missing:
        missing.setitem(sys.modules, 'pydantic', None)
        missing.setitem(sys.modules, 'pydantic_handlebars', None)
        from logfire.variables import VariablesConfig

        with pytest.raises(ImportError, match=r'logfire\[variables\]'):
            VariablesConfig(variables={})
        with pytest.raises(ImportError, match=r'logfire\[variables\]'):
            VariablesConfig.model_validate({'variables': {}})
        with pytest.raises(ImportError, match=r'logfire\[variables\]'):
            getattr(logfire.variables, 'Variable')
        deferred_config_type = getattr(logfire.variables, 'VariablesConfig')
        with pytest.raises(ImportError, match=r'logfire\[variables\]'):
            isinstance(config, deferred_config_type)
        with pytest.raises(ImportError, match=r'logfire\[variables\]'):
            issubclass(RealVariablesConfig, deferred_config_type)

    assert isinstance(VariablesConfig(variables={}), RealVariablesConfig)
    assert isinstance(VariablesConfig.model_validate({'variables': {}}), RealVariablesConfig)


@pytest.mark.parametrize('check', ['instance', 'subclass'])
def test_retained_variables_config_type_checks(check: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from logfire.variables.config import VariablesConfig as RealVariablesConfig

    with monkeypatch.context() as missing:
        missing.setitem(sys.modules, 'pydantic', None)
        missing.setitem(sys.modules, 'pydantic_handlebars', None)
        from logfire.variables import VariablesConfig

    if check == 'instance':
        assert isinstance(VariablesConfig(variables={}), VariablesConfig)
        assert isinstance(RealVariablesConfig(variables={}), VariablesConfig)
        assert not isinstance(object(), VariablesConfig)
    else:
        assert issubclass(RealVariablesConfig, VariablesConfig)
        assert not issubclass(int, VariablesConfig)
