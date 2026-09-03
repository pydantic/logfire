"""Exercise the installed Pydantic entry point in genuinely fresh processes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic.version import VERSION

from logfire._internal.utils import get_version

requires_supported_plugin = pytest.mark.skipif(
    get_version(VERSION) < get_version('2.5.0'),
    reason='Pydantic instrumentation and its cloudpickle workaround require Pydantic >= 2.5.',
)


def run_script(script: str, cwd: Path, **settings: str) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith('LOGFIRE_')}
    env.pop('PYDANTIC_DISABLE_PLUGINS', None)
    env.update(LOGFIRE_SEND_TO_LOGFIRE='false', **settings)
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=cwd, env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('record', [None, '', 'off'])
def test_entry_point_module_does_not_import_logfire_sdk(tmp_path: Path, record: str | None) -> None:
    settings = {} if record is None else {'LOGFIRE_PYDANTIC_RECORD': record}
    run_script(
        """
import sys
from importlib.metadata import entry_points
from pydantic import BaseModel

entry = next(e for e in entry_points(group='pydantic') if e.name == 'logfire-plugin')
entry.load()
class Model(BaseModel):
    value: int
assert Model(value='1').value == 1
assert 'logfire' not in sys.modules
assert not any(name.startswith('opentelemetry') for name in sys.modules)
""",
        tmp_path,
        **settings,
    )


@requires_supported_plugin
def test_disabled_plugin_preserves_cloudpickle_compatibility(tmp_path: Path) -> None:
    run_script(
        """
import sys
import cloudpickle
from pydantic import BaseModel
class Model(BaseModel):
    value: int
model = Model(value=1)
assert cloudpickle.loads(cloudpickle.dumps(model)).model_dump() == {'value': 1}
assert 'logfire' not in sys.modules
""",
        tmp_path,
    )


@pytest.mark.parametrize(
    'source',
    ['environment', 'model', 'file', 'configured_file', pytest.param('instrument', marks=requires_supported_plugin)],
)
def test_entry_point_records_when_enabled(tmp_path: Path, source: str) -> None:
    setup = ''
    model_settings = ''
    settings: dict[str, str] = {}
    if source == 'environment':
        settings['LOGFIRE_PYDANTIC_PLUGIN_RECORD'] = 'all'
    elif source == 'model':
        model_settings = ", plugin_settings={'logfire': {'record': 'all'}}"
    elif source in ('file', 'configured_file'):
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        (config_dir / 'pyproject.toml').write_text('[tool.logfire]\npydantic_plugin_record = "all"\n')
        if source == 'file':
            settings['LOGFIRE_CONFIG_DIR'] = str(config_dir)
        else:
            setup = f'import logfire\nlogfire.configure(send_to_logfire=False, config_dir={str(config_dir)!r})\n'
    else:
        setup = 'import logfire\nlogfire.instrument_pydantic()\n'
    run_script(
        f"""
import sys
from pydantic import BaseModel
from pydantic.version import VERSION
{setup}
class Model(BaseModel{model_settings}):
    value: int
assert Model(value='1').value == 1
if tuple(map(int, VERSION.split('.')[:2])) >= (2, 5):
    assert 'logfire.integrations.pydantic' in sys.modules
    import logfire
    from logfire.testing import TestExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    exporter = TestExporter()
    logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[SimpleSpanProcessor(exporter)])
    Model(value=2)
    spans = exporter.exported_spans_as_dict()
    assert len(spans) == 1
    assert spans[0]['name'] == 'pydantic.validate_python'
    assert spans[0]['attributes']['success'] is True
""",
        tmp_path,
        **settings,
    )


def test_global_disable_overrides_model_settings(tmp_path: Path) -> None:
    run_script(
        """
import sys
from pydantic import BaseModel
class Model(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
    value: int
assert Model(value='1').value == 1
assert 'logfire' not in sys.modules
""",
        tmp_path,
        LOGFIRE_PYDANTIC_RECORD='off',
    )


def test_invalid_config_preserves_configuration_error(tmp_path: Path) -> None:
    (tmp_path / 'pyproject.toml').write_text('[invalid toml')
    run_script(
        """
from pydantic import BaseModel
from pydantic.version import VERSION
if tuple(map(int, VERSION.split('.')[:2])) >= (2, 5):
    try:
        class Model(BaseModel):
            value: int
    except Exception as exc:
        assert type(exc).__name__ == 'LogfireConfigError', repr(exc)
        assert 'Invalid config file:' in str(exc)
    else:
        raise AssertionError('Invalid config should retain the SDK error')
""",
        tmp_path,
    )


def test_keyword_plugin_protocol_call_stays_lazy(tmp_path: Path) -> None:
    run_script(
        """
import sys
from pydantic_core import core_schema
from logfire_pydantic_plugin import plugin
assert plugin.new_schema_validator(
    schema=core_schema.int_schema(), schema_type=int, schema_type_path=None,
    schema_kind='TypeAdapter', config=None, plugin_settings={},
) == (None, None, None)
assert 'logfire' not in sys.modules
""",
        tmp_path,
    )
