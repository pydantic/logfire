from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, call, patch

import pytest
from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

import logfire._internal.cli
from logfire._internal.cli import SplitArgs, main
from logfire._internal.cli.run import (
    OTEL_INSTRUMENTATION_MAP,
    InstrumentationRecommendation,
    collect_instrumentation_context,
    find_recommended_instrumentations_to_install,
    get_recommendation_texts,
    instrument_packages,
    instrumented_packages_text,
)
from logfire._internal.config import LogfireCredentials
from logfire.testing import TestExporter
from tests.import_used_for_tests import run_script_test

HTTPX_OTEL_PACKAGE = 'opentelemetry-instrumentation-httpx'
PSYCOPG_OTEL_PACKAGES = {
    'opentelemetry-instrumentation-psycopg': 'psycopg',
    'opentelemetry-instrumentation-psycopg2': 'psycopg',
}


@pytest.fixture
def logfire_credentials() -> LogfireCredentials:
    return LogfireCredentials(
        token='token',
        project_name='my-project',
        project_url='https://dashboard.logfire.dev',
        logfire_api_url='https://logfire-us.pydantic.dev',
    )


def test_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    out = capsys.readouterr().out
    assert 'inspect' in out
    assert 'run' in out
    assert 'gateway' not in out


@pytest.mark.parametrize('command', ['auth', 'clean', 'gateway', 'whoami', 'prompt', 'info'])
def test_removed_commands(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match='2'):
        main([command])
    assert 'invalid choice' in capsys.readouterr().err


def test_nice_interrupt(capsys: pytest.CaptureFixture[str]) -> None:
    with patch('logfire._internal.cli._main', side_effect=KeyboardInterrupt):
        try:
            main([])
        except SystemExit:
            pass
        assert capsys.readouterr().err == 'User cancelled.\n'


@pytest.mark.parametrize('configured', [False, True])
@pytest.mark.parametrize('module', [False, True])
def test_run_preserves_application_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: bool, module: bool
) -> None:
    script = tmp_path / 'logging_app.py'
    script.write_text(
        """
import json
import logging
import sys

import logfire._internal.cli
import urllib3

if sys.argv[-1] == 'configured':
    logging.basicConfig(level=logging.ERROR, format='APP:%(levelname)s:%(message)s')

print(json.dumps({
    'root_level': logging.getLogger().level,
    'root_handlers': len(logging.getLogger().handlers),
    'cli_level': logging.getLogger('logfire._internal.cli').level,
    'cli_handlers': len(logging.getLogger('logfire._internal.cli').handlers),
    'urllib3_level': logging.getLogger('urllib3').level,
    'urllib3_handlers': len(logging.getLogger('urllib3').handlers),
}))
logging.basicConfig(level=logging.INFO, format='APP:%(levelname)s:%(message)s')
logging.getLogger('application').info('application message')
logging.getLogger('urllib3.connectionpool').info('HTTP client message')
logging.error('application error')
"""
    )
    monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
    monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
    target = ['-m', 'logging_app'] if module else [str(script)]
    target.append('configured' if configured else 'unconfigured')
    direct = subprocess.run([sys.executable, *target], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    wrapped = subprocess.run(
        [
            sys.executable,
            '-m',
            'logfire',
            'run',
            '--no-summary',
            '--exclude',
            ','.join(sorted(set(OTEL_INSTRUMENTATION_MAP.values()))),
            *target,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert direct.returncode == 0, direct.stderr
    assert wrapped.returncode == 0, wrapped.stderr
    assert wrapped.stdout == direct.stdout
    # The unrelated global-tracer-provider warning can precede application output.
    assert [line for line in wrapped.stderr.splitlines() if line.startswith('APP:')] == direct.stderr.splitlines()


def test_inspect(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    os.environ['COLUMNS'] = '150'
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    with pytest.raises(SystemExit):
        main(['inspect'])
    assert capsys.readouterr().err == snapshot("""\


╭───────────────────────────────────────────────────────────────── Logfire Summary ──────────────────────────────────────────────────────────────────╮
│                                                                                                                                                    │
│  ☐ jinja2 (need to install opentelemetry-instrumentation-jinja2)                                                                                   │
│  ☐ pymysql (need to install opentelemetry-instrumentation-pymysql)                                                                                 │
│  ☐ urllib [*] (need to install opentelemetry-instrumentation-urllib)                                                                               │
│                                                                                                                                                    │
│  [*] `urllib` may not actually be used by your app, in which case you can ignore this recommendation                                               │
│                                                                                                                                                    │
│                                                                                                                                                    │
│  To install all recommended packages at once, run:                                                                                                 │
│                                                                                                                                                    │
│  uv add 'logfire[urllib]' opentelemetry-instrumentation-jinja2 opentelemetry-instrumentation-pymysql                                               │
│                                                                                                                                                    │
│  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────  │
│                                                                                                                                                    │
│  To hide this summary box, use: logfire run --no-summary.                                                                                          │
│                                                                                                                                                    │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

""")


@pytest.mark.parametrize('has_uv', [True, False])
@pytest.mark.parametrize(
    ('installed', 'requirements'),
    [
        (['requests'], ["'logfire[requests]'"]),
        (['pymysql'], ['opentelemetry-instrumentation-pymysql']),
        (['requests', 'pymysql'], ["'logfire[requests]'", 'opentelemetry-instrumentation-pymysql']),
        (['psycopg', 'psycopg2'], ["'logfire[psycopg,psycopg2]'"]),
        (['psycopg', 'psycopg2', 'opentelemetry-instrumentation-psycopg'], ["'logfire[psycopg2]'"]),
    ],
)
def test_inspect_install_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    has_uv: bool,
    installed: list[str],
    requirements: list[str],
) -> None:
    for name in installed:
        metadata_dir = tmp_path / f'{name}-1.0.dist-info'
        metadata_dir.mkdir()
        (metadata_dir / 'METADATA').write_text(f'Name: {name}\nVersion: 1.0\n')
    monkeypatch.setattr(
        importlib.metadata, 'distributions', lambda: importlib.metadata.Distribution.discover(path=[str(tmp_path)])
    )

    def find_uv(name: str) -> str | None:
        return '/bin/uv' if has_uv else None

    monkeypatch.setattr(shutil, 'which', find_uv)
    monkeypatch.setenv('COLUMNS', '150')

    with pytest.raises(SystemExit) as exc_info:
        main(['inspect', '--ignore', 'sqlite3,urllib'])

    assert exc_info.value.code == 1
    output = capsys.readouterr().err
    commands = [line.strip('│ ') for line in output.splitlines() if 'uv add ' in line or 'pip install ' in line]
    installer = 'uv add' if has_uv else 'pip install'
    assert commands == [f'{installer} {" ".join(requirements)}']


@pytest.mark.parametrize(
    ('otel_instrumentation_map', 'installed', 'should_install'),
    [
        (
            {
                'opentelemetry-instrumentation-fastapi': 'fastapi',
                'opentelemetry-instrumentation-urllib': 'urllib',
                'opentelemetry-instrumentation-sqlite3': 'sqlite3',
            },
            {'fastapi'},
            snapshot(
                {
                    InstrumentationRecommendation('opentelemetry-instrumentation-fastapi', ('fastapi',)),
                    InstrumentationRecommendation('opentelemetry-instrumentation-urllib', ('urllib',)),
                    InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
                }
            ),
        ),
        (
            {
                'opentelemetry-instrumentation-fastapi': 'fastapi',
                'opentelemetry-instrumentation-starlette': 'starlette',
            },
            {'fastapi', 'starlette'},
            snapshot({InstrumentationRecommendation('opentelemetry-instrumentation-fastapi', ('fastapi',))}),
        ),
        (
            {
                'opentelemetry-instrumentation-urllib3': 'urllib3',
                'opentelemetry-instrumentation-requests': 'requests',
                'opentelemetry-instrumentation-sqlite3': 'sqlite3',
            },
            {'urllib3', 'requests'},
            snapshot(
                {
                    InstrumentationRecommendation('opentelemetry-instrumentation-requests', ('requests',)),
                    InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
                }
            ),
        ),
        (
            {'opentelemetry-instrumentation-starlette': 'starlette'},
            {'starlette'},
            snapshot({InstrumentationRecommendation('opentelemetry-instrumentation-starlette', ('starlette',))}),
        ),
    ],
)
def test_recommended_packages_with_dependencies(
    otel_instrumentation_map: dict[str, str],
    installed: set[str],
    should_install: set[InstrumentationRecommendation],
) -> None:
    recommendations = find_recommended_instrumentations_to_install(otel_instrumentation_map, set(), installed)
    assert recommendations == should_install


@pytest.mark.parametrize(
    ('installed_clients', 'otel_version', 'expected'),
    [
        (
            {'httpx'},
            None,
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx',)),
        ),
        (
            {'httpx2'},
            None,
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx2',), '0.65b0'),
        ),
        (
            {'httpx', 'httpx2'},
            None,
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx', 'httpx2'), '0.65b0'),
        ),
        ({'httpx'}, '0.64b0', None),
        (
            {'httpx2'},
            '0.64b0',
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx2',), '0.65b0', already_installed=True),
        ),
        (
            {'httpx', 'httpx2'},
            '0.64b0',
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx2',), '0.65b0', already_installed=True),
        ),
        ({'httpx2'}, '0.65b0', None),
        ({'httpx', 'httpx2'}, '0.65b0', None),
    ],
)
def test_httpx_recommendations(
    installed_clients: set[str],
    otel_version: str | None,
    expected: InstrumentationRecommendation | None,
) -> None:
    installed_otel: set[str] = {HTTPX_OTEL_PACKAGE} if otel_version else set()
    installed_versions = {HTTPX_OTEL_PACKAGE: otel_version} if otel_version else {}

    recommendations = find_recommended_instrumentations_to_install(
        {HTTPX_OTEL_PACKAGE: 'httpx'},
        installed_otel,
        installed_clients,
        installed_versions,
    )

    assert recommendations == ({expected} if expected else set())


@pytest.mark.parametrize('excluded_client', ['httpx', 'httpx2'])
def test_httpx_exclude_aliases(excluded_client: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logfire._internal.cli.run, 'installed_packages', lambda: {'httpx2'})

    context = collect_instrumentation_context({excluded_client})

    assert HTTPX_OTEL_PACKAGE not in context.instrument_pkg_map
    assert all(HTTPX_OTEL_PACKAGE != recommendation.package_name for recommendation in context.recommendations)


@pytest.mark.parametrize(
    ('installed_clients', 'expected'),
    [
        (
            {'psycopg'},
            {InstrumentationRecommendation('opentelemetry-instrumentation-psycopg', ('psycopg',))},
        ),
        (
            {'psycopg2'},
            {InstrumentationRecommendation('opentelemetry-instrumentation-psycopg2', ('psycopg2',))},
        ),
        (
            {'psycopg2-binary'},
            {InstrumentationRecommendation('opentelemetry-instrumentation-psycopg2', ('psycopg2',))},
        ),
        (
            {'psycopg', 'psycopg2-binary'},
            {
                InstrumentationRecommendation('opentelemetry-instrumentation-psycopg', ('psycopg',)),
                InstrumentationRecommendation('opentelemetry-instrumentation-psycopg2', ('psycopg2',)),
            },
        ),
    ],
)
def test_psycopg_recommendations(installed_clients: set[str], expected: set[InstrumentationRecommendation]) -> None:
    recommendations = find_recommended_instrumentations_to_install(
        PSYCOPG_OTEL_PACKAGES,
        set(),
        installed_clients,
    )

    assert recommendations == expected


def test_instrument_packages_calls_instrument(monkeypatch: pytest.MonkeyPatch):
    fake_logfire = types.SimpleNamespace()
    called = {}

    def make_instrument(name: str):
        def f():
            called[name] = True

        return f

    fake_logfire.instrument_foo = make_instrument('foo')
    monkeypatch.setattr(logfire._internal.cli.run, 'logfire', fake_logfire)
    installed_otel = {'opentelemetry-instrumentation-foo'}
    instrument_pkg_map = {'opentelemetry-instrumentation-foo': 'foo'}
    result = instrument_packages(installed_otel, instrument_pkg_map)
    assert result == snapshot(['foo'])
    assert called['foo'] is True


def test_instrument_packages_with_only_httpx2(monkeypatch: pytest.MonkeyPatch) -> None:
    instrument_httpx = Mock()
    monkeypatch.setattr(logfire._internal.cli.run, 'logfire', types.SimpleNamespace(instrument_httpx=instrument_httpx))
    monkeypatch.setattr(
        logfire._internal.cli.run,
        'installed_packages',
        lambda: {HTTPX_OTEL_PACKAGE, 'httpx2'},
    )
    monkeypatch.setattr(
        logfire._internal.cli.run,
        '_installed_package_versions',
        Mock(return_value={HTTPX_OTEL_PACKAGE: '0.65b0'}),
    )

    context = collect_instrumentation_context(())
    result = instrument_packages(context.installed_otel_pkgs, context.instrument_pkg_map)
    summary = instrumented_packages_text(
        context.installed_otel_pkgs,
        result,
        context.installed_pkgs,
        context.installed_versions,
    )

    assert result == ['httpx']
    instrument_httpx.assert_called_once_with()
    assert '✓ httpx2 (installed and instrumented)' in summary


def test_instrument_packages_targets_each_psycopg_family(monkeypatch: pytest.MonkeyPatch) -> None:
    instrument_psycopg = Mock()
    monkeypatch.setattr(
        logfire._internal.cli.run,
        'logfire',
        types.SimpleNamespace(instrument_psycopg=instrument_psycopg),
    )

    result = instrument_packages(set(PSYCOPG_OTEL_PACKAGES), PSYCOPG_OTEL_PACKAGES)

    assert result == ['psycopg', 'psycopg2']
    assert instrument_psycopg.call_args_list == [call('psycopg'), call('psycopg2')]


@pytest.mark.parametrize(
    ('installed_clients', 'otel_version', 'instrumented', 'expected_lines'),
    [
        ({'httpx'}, '0.64b0', ['httpx'], ['✓ httpx (installed and instrumented)']),
        ({'httpx2'}, '0.65b0', ['httpx'], ['✓ httpx2 (installed and instrumented)']),
        (
            {'httpx', 'httpx2'},
            '0.65b0',
            ['httpx'],
            ['✓ httpx (installed and instrumented)', '✓ httpx2 (installed and instrumented)'],
        ),
        ({'httpx2'}, '0.64b0', [], ['⚠️ httpx2 (installed but not automatically instrumented)']),
        (
            {'httpx', 'httpx2'},
            '0.64b0',
            ['httpx'],
            ['✓ httpx (installed and instrumented)', '⚠️ httpx2 (installed but not automatically instrumented)'],
        ),
    ],
)
def test_httpx_instrumented_packages_text(
    installed_clients: set[str],
    otel_version: str,
    instrumented: list[str],
    expected_lines: list[str],
) -> None:
    text = instrumented_packages_text(
        {HTTPX_OTEL_PACKAGE},
        instrumented,
        installed_clients,
        {HTTPX_OTEL_PACKAGE: otel_version},
    )

    assert [line for line in str(text).splitlines() if line] == ['Your instrumentation checklist:', *expected_lines]


def test_instrumented_packages_text_basic():
    installed_otel_pkgs = {'opentelemetry-instrumentation-foo', 'opentelemetry-instrumentation-bar'}
    instrumented_packages = ['foo']
    installed_pkgs = {'foo', 'bar'}
    text = instrumented_packages_text(installed_otel_pkgs.copy(), instrumented_packages, installed_pkgs)
    assert '✓ foo' in text
    assert '⚠️ bar' in text


def test_get_recommendation_texts(monkeypatch: pytest.MonkeyPatch):
    recs = {
        InstrumentationRecommendation('opentelemetry-instrumentation-foo', ('foo',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-bar', ('bar',)),
    }
    recommended, install = get_recommendation_texts(recs)
    assert 'uv add opentelemetry-instrumentation-bar opentelemetry-instrumentation-foo' in install
    assert 'need to install opentelemetry-instrumentation-bar' in recommended
    assert 'need to install opentelemetry-instrumentation-foo' in recommended

    monkeypatch.setattr(logfire._internal.cli.run, 'is_uv_installed', lambda: False)
    _, install = get_recommendation_texts(recs)
    assert 'pip install opentelemetry-instrumentation-bar opentelemetry-instrumentation-foo' in install


def test_get_recommendation_texts_httpx2_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    recs = {
        InstrumentationRecommendation(
            HTTPX_OTEL_PACKAGE,
            ('httpx2',),
            '0.65b0',
            already_installed=True,
        )
    }

    recommended, install = get_recommendation_texts(recs)

    assert 'httpx2 (need to upgrade opentelemetry-instrumentation-httpx>=0.65b0)' in recommended
    assert "uv add 'logfire[httpx]' 'opentelemetry-instrumentation-httpx>=0.65b0'" in install

    monkeypatch.setattr(logfire._internal.cli.run, 'is_uv_installed', lambda: False)
    _, install = get_recommendation_texts(recs)
    assert "pip install -U 'logfire[httpx]' 'opentelemetry-instrumentation-httpx>=0.65b0'" in install


@pytest.mark.parametrize(
    ('targets', 'formatted_targets'),
    [
        (('foo', 'bar'), 'foo and bar'),
        (('foo', 'bar', 'baz'), 'foo, bar, and baz'),
    ],
)
def test_get_recommendation_texts_formats_multiple_targets(targets: tuple[str, ...], formatted_targets: str) -> None:
    recommended, _ = get_recommendation_texts(
        {InstrumentationRecommendation('opentelemetry-instrumentation-foo', targets)}
    )

    assert f'{formatted_targets} (need to install opentelemetry-instrumentation-foo)' in recommended


def test_get_recommendation_texts_marks_ambiguous_packages():
    recs = {
        InstrumentationRecommendation('opentelemetry-instrumentation-foo', ('foo',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-requests', ('requests',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-urllib', ('urllib',)),
    }
    recommended, _ = get_recommendation_texts(recs)

    assert '☐ foo (need to install opentelemetry-instrumentation-foo)' in recommended
    assert '☐ requests [*] (need to install opentelemetry-instrumentation-requests)' in recommended
    assert '☐ sqlite3 [*] (need to install opentelemetry-instrumentation-sqlite3)' in recommended
    assert '☐ urllib [*] (need to install opentelemetry-instrumentation-urllib)' in recommended
    assert (
        '[*] `requests`, `sqlite3`, and `urllib` may not actually be used by your app, '
        'in which case you can ignore these recommendations'
    ) in recommended


def test_get_recommendation_texts_formats_two_ambiguous_packages():
    recs = {
        InstrumentationRecommendation('opentelemetry-instrumentation-requests', ('requests',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
    }
    recommended, _ = get_recommendation_texts(recs)

    assert (
        '[*] `requests` and `sqlite3` may not actually be used by your app, '
        'in which case you can ignore these recommendations'
    ) in recommended


def test_instrument_packages_openai() -> None:
    instrument_packages({'openai'}, {'openai': 'openai'})

    import openai

    client = openai.Client(api_key='test-key')
    assert getattr(client, '_is_instrumented_by_logfire', False) is True


def test_instrument_packages_aiohttp_server() -> None:
    try:
        instrument_packages(
            {'opentelemetry-instrumentation-aiohttp-server'},
            {'opentelemetry-instrumentation-aiohttp-server': 'aiohttp_server'},
        )

        import aiohttp.web

        app = aiohttp.web.Application()
        assert app.middlewares[0].__module__ == 'opentelemetry.instrumentation.aiohttp_server'
    finally:
        from opentelemetry.instrumentation.aiohttp_server import AioHttpServerInstrumentor

        AioHttpServerInstrumentor().uninstrument()


async def test_instrument_packages_aiohttp_client() -> None:
    try:
        instrument_packages(
            {'opentelemetry-instrumentation-aiohttp-client'},
            {'opentelemetry-instrumentation-aiohttp-client': 'aiohttp_client'},
        )

        import aiohttp.client

        async with aiohttp.client.ClientSession() as client:
            assert getattr(client.trace_configs[0], '_is_instrumented_by_opentelemetry', False) is True
    finally:
        from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

        AioHttpClientInstrumentor().uninstrument()


def test_instrument_packages_falls_back_to_botocore_instrumentor(exporter: TestExporter) -> None:
    import boto3
    from botocore.stub import Stubber
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

    try:
        result = instrument_packages(
            {'opentelemetry-instrumentation-botocore'},
            {'opentelemetry-instrumentation-botocore': 'botocore'},
        )

        # boto3 and botocore are only partially typed.
        client = cast(Any, boto3).client(
            's3', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test'
        )
        with cast(Any, Stubber(client)) as stubber:
            stubber.add_response('list_buckets', {'Buckets': []})
            client.list_buckets()
    finally:
        BotocoreInstrumentor().uninstrument()

    assert result == snapshot(['botocore'])
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'S3.ListBuckets',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'rpc.system': 'aws-api',
                    'rpc.service': 'S3',
                    'rpc.method': 'ListBuckets',
                    'cloud.region': 'us-east-1',
                    'server.address': 's3.amazonaws.com',
                    'server.port': 443,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'S3.ListBuckets',
                },
            }
        ]
    )


class _FakeInstrumentor(BaseInstrumentor):
    """Records the keyword arguments it's instrumented with. Make subclasses with `_fake_instrumentor()`."""

    dependencies: tuple[str, ...] = ()
    instrument_calls: list[dict[str, Any]]

    def instrumentation_dependencies(self) -> tuple[str, ...]:
        return self.dependencies

    def _instrument(self, **kwargs: Any) -> None:
        self.instrument_calls.append(kwargs)

    def _uninstrument(self, **kwargs: Any) -> None:
        pass


def _fake_instrumentor(*dependencies: str) -> type[_FakeInstrumentor]:
    """Make a new instrumentor class, because instrumentors are singletons per class."""

    class FakeInstrumentor(_FakeInstrumentor):
        pass

    FakeInstrumentor.dependencies = dependencies
    FakeInstrumentor.instrument_calls = []
    return FakeInstrumentor


def _install_fake_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package: str,
    requires: tuple[str, ...] = (),
    **instrumentors: object,
) -> None:
    """Install `opentelemetry-instrumentation-<package>` with `instrumentors` as its entry points, in that order.

    `requires` are the libraries it instruments, i.e. its `instruments` extra.
    """
    module_name = f'logfire_test_instrumentors_{package}'
    monkeypatch.setitem(sys.modules, module_name, types.SimpleNamespace(**instrumentors))
    dist_info = tmp_path / f'opentelemetry_instrumentation_{package}-1.0.dist-info'
    dist_info.mkdir()
    requirements = ''.join(f'Requires-Dist: {requirement}; extra == "instruments"\n' for requirement in requires)
    (dist_info / 'METADATA').write_text(f'Name: opentelemetry-instrumentation-{package}\nVersion: 1.0\n{requirements}')
    entry_points = ''.join(f'{name} = {module_name}:{name}\n' for name in instrumentors)
    (dist_info / 'entry_points.txt').write_text(f'[opentelemetry_instrumentor]\n{entry_points}')
    monkeypatch.setattr(sys, 'path', [str(tmp_path), *sys.path])


def _instrument_fallback_packages(*packages: str) -> list[str]:
    """Call `instrument_packages()` for packages without a Logfire method, so they use the fallback."""
    otel_packages = {f'opentelemetry-instrumentation-{package}': package for package in packages}
    return instrument_packages(set(otel_packages), otel_packages)


def test_instrument_packages_fallback_activates_every_usable_instrumentor_with_logfire_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_library = _fake_instrumentor('logfire-test-missing-library')
    first = _fake_instrumentor()
    second = _fake_instrumentor()
    # Like botocore's package, which registers the aiobotocore instrumentor before the botocore one.
    _install_fake_package(tmp_path, monkeypatch, 'foo', missing_library=missing_library, first=first, second=second)

    assert _instrument_fallback_packages('foo') == ['foo']
    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    providers = {
        'tracer_provider': config.get_tracer_provider(),
        'meter_provider': config.get_meter_provider(),
        'logger_provider': config.get_logger_provider(),
    }
    assert missing_library.instrument_calls == []
    assert first.instrument_calls == [providers]
    assert second.instrument_calls == [providers]


def test_instrument_packages_fallback_skips_missing_libraries_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # foo's package requires a library that isn't installed.
    _install_fake_package(tmp_path, monkeypatch, 'foo', requires=('logfire-test-missing-library',))
    # bar's package is usable, but this instrumentor needs a library that isn't installed.
    _install_fake_package(
        tmp_path, monkeypatch, 'bar', missing_library=_fake_instrumentor('logfire-test-missing-library')
    )

    # The test suite turns warnings into errors, so this also checks that nothing warns.
    assert _instrument_fallback_packages('foo', 'bar') == []


@pytest.mark.parametrize(
    'error',
    [
        pytest.param(RuntimeError('broken instrumentor'), id='error'),
        # Only a missing library is skipped quietly; a missing module warns like any other failure.
        pytest.param(ModuleNotFoundError("No module named 'missing'"), id='missing-module'),
    ],
)
def test_instrument_packages_fallback_warns_on_broken_instrumentor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    _install_fake_package(tmp_path, monkeypatch, 'foo', broken=Mock(side_effect=error))

    with pytest.warns(UserWarning) as warnings_record:
        result = _instrument_fallback_packages('foo')

    assert result == []
    assert [str(w.message) for w in warnings_record] == [
        f'Failed to instrument with logfire_test_instrumentors_foo:broken: {error!r}'
    ]


def test_instrument_packages_fallback_warns_when_package_requirements_cannot_be_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # OpenTelemetry can't parse this requirement, like old OpenTelemetry versions can't read any distribution.
    _install_fake_package(tmp_path, monkeypatch, 'foo', requires=('not valid!',), foo=_fake_instrumentor())

    with pytest.warns(UserWarning) as warnings_record:
        result = _instrument_fallback_packages('foo')

    assert result == []
    # The explanation comes from `packaging`.
    assert [str(w.message) for w in warnings_record] == [
        IsStr(regex=r'Failed to instrument with opentelemetry-instrumentation-foo: InvalidRequirement\(.*')
    ]


def test_instrument_packages_fallback_warns_when_entry_points_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_package(tmp_path, monkeypatch, 'foo')
    # An entry point needs `name = module:attribute`, so a line without `=` is malformed.
    (tmp_path / 'opentelemetry_instrumentation_foo-1.0.dist-info' / 'entry_points.txt').write_text(
        '[opentelemetry_instrumentor]\nfoo\n'
    )

    with pytest.warns(UserWarning) as warnings_record:
        result = _instrument_fallback_packages('foo')

    assert result == []
    # The explanation comes from `importlib.metadata`.
    assert [str(w.message) for w in warnings_record] == [
        IsStr(regex=r'Failed to instrument with opentelemetry-instrumentation-foo: TypeError\(.*')
    ]


@pytest.mark.parametrize(
    'requires, dependencies, message',
    [
        pytest.param(
            ('pytest>=999',),
            (),
            r'Failed to instrument with opentelemetry-instrumentation-foo: .*pytest>=999.*',
            id='package',
        ),
        pytest.param(
            (),
            ('pytest>=999',),
            r'Failed to instrument with logfire_test_instrumentors_foo:foo: .*pytest>=999.*',
            id='instrumentor',
        ),
    ],
)
def test_instrument_packages_fallback_warns_on_unsupported_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    requires: tuple[str, ...],
    dependencies: tuple[str, ...],
    message: str,
) -> None:
    # pytest is installed, but no version of it satisfies `pytest>=999`.
    _install_fake_package(tmp_path, monkeypatch, 'foo', requires=requires, foo=_fake_instrumentor(*dependencies))

    with pytest.warns(UserWarning) as warnings_record:
        result = _instrument_fallback_packages('foo')

    assert result == []
    # OpenTelemetry's explanation includes the installed pytest version.
    assert [str(w.message) for w in warnings_record] == [IsStr(regex=message)]


def test_instrument_packages_no_fallback_when_logfire_method_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usable = _fake_instrumentor()
    _install_fake_package(tmp_path, monkeypatch, 'foo', foo=usable)
    fake_logfire = types.SimpleNamespace(instrument_foo=Mock(side_effect=RuntimeError('instrumentation failed')))
    monkeypatch.setattr(logfire._internal.cli.run, 'logfire', fake_logfire)

    result = instrument_packages({'opentelemetry-instrumentation-foo'}, {'opentelemetry-instrumentation-foo': 'foo'})

    assert result == []
    fake_logfire.instrument_foo.assert_called_once_with()
    assert usable.instrument_calls == []


def test_split_args_action() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--foo', action=SplitArgs)
    args = parser.parse_args(['--foo', 'a,b,c'])
    assert args.foo == ['a', 'b', 'c']


def test_instrumented_packages_text_filters_starlette_and_urllib3():
    # Both special cases: fastapi/starlette and requests/urllib3
    installed_otel_pkgs = {
        'opentelemetry-instrumentation-fastapi',
        'opentelemetry-instrumentation-starlette',
        'opentelemetry-instrumentation-requests',
        'opentelemetry-instrumentation-urllib3',
    }
    instrumented_packages = ['fastapi', 'starlette', 'requests', 'urllib3']
    installed_pkgs = {'fastapi', 'starlette', 'requests', 'urllib3'}

    text = instrumented_packages_text(installed_otel_pkgs, instrumented_packages, installed_pkgs)
    assert str(text) == snapshot(
        """\
Your instrumentation checklist:

✓ fastapi (installed and instrumented)
✓ requests (installed and instrumented)
"""
    )


@pytest.mark.parametrize('fastapi_instrumentor_installed', [False, True])
def test_instrumented_packages_text_shows_starlette_without_fastapi_instrumentation(
    fastapi_instrumentor_installed: bool,
) -> None:
    installed_otel_pkgs = {'opentelemetry-instrumentation-starlette'}
    if fastapi_instrumentor_installed:
        installed_otel_pkgs.add('opentelemetry-instrumentation-fastapi')
    text = instrumented_packages_text(installed_otel_pkgs, ['starlette'], {'fastapi', 'starlette'})
    assert '✓ starlette (installed and instrumented)' in str(text)


def test_parse_run_no_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_with_entry_points', Mock(return_value=False))

    with pytest.raises(SystemExit):
        main(['run', '--no-summary'])

    assert configure_mock.call_count == 1


@pytest.mark.parametrize('module', [False, True])
def test_parse_run_global_tracer_in_fresh_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: bool
) -> None:
    script = tmp_path / 'traced_app.py'
    script.write_text(
        """
import json

from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import TestExporter

exporter = TestExporter()
logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[SimpleSpanProcessor(exporter)])
with trace.get_tracer('demo').start_as_current_span('otel parent'):
    with logfire.span('native child'):
        pass
print(json.dumps(exporter.exported_spans_as_dict()))
"""
    )
    monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
    monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
    target = ['-m', 'traced_app'] if module else [str(script)]
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'logfire',
            'run',
            '--exclude',
            ','.join(sorted(set(OTEL_INSTRUMENTATION_MAP.values()))),
            *target,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    spans = json.loads(result.stdout)
    assert [span['name'] for span in spans] == ['native child', 'otel parent']
    child, parent = spans
    assert child['parent'] == parent['context']
    assert child['context']['trace_id'] == parent['context']['trace_id']
    assert 'Overriding of current TracerProvider is not allowed' not in result.stderr


@pytest.mark.parametrize('module', [False, True])
@pytest.mark.parametrize('exclude_flask', [False, True])
def test_parse_run_flask_in_fresh_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: bool, exclude_flask: bool
) -> None:
    script = tmp_path / 'flask_app.py'
    script.write_text(
        """
import json

from flask import Flask
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import logfire
from logfire.testing import TestExporter

exporter = TestExporter()
logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[SimpleSpanProcessor(exporter)])
app = Flask(__name__)

@app.get('/')
def homepage():
    return 'hello'

response = app.test_client().get('/')
assert response.status_code == 200
assert response.text == 'hello'
print(json.dumps(exporter.exported_spans_as_dict()))
"""
    )
    monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
    monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
    # Exercise discovery and dispatch with only Flask enabled, regardless of other installed integrations.
    excluded = set(OTEL_INSTRUMENTATION_MAP.values()) - {'flask'}
    if exclude_flask:
        excluded.add('flask')
    target = ['-m', 'flask_app'] if module else [str(script)]
    result = subprocess.run(
        [sys.executable, '-m', 'logfire', 'run', '--summary', '--exclude', ','.join(sorted(excluded)), *target],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    spans = json.loads(result.stdout)
    if exclude_flask:
        assert spans == []
        assert 'flask (installed and instrumented)' not in result.stderr
    else:
        assert [span['name'] for span in spans] == ['GET /']
        assert spans[0]['attributes']['http.route'] == '/'
        assert spans[0]['attributes']['http.status_code'] == 200
        assert spans[0]['attributes']['logfire.msg'] == 'GET /'
        assert 'flask (installed and instrumented)' in result.stderr


@pytest.mark.parametrize('module', [False, True])
@pytest.mark.parametrize('exclude_starlette', [False, True])
def test_parse_run_starlette_in_fresh_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: bool, exclude_starlette: bool
) -> None:
    script = tmp_path / 'starlette_app.py'
    script.write_text(
        """
import json

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import logfire
from logfire.testing import TestExporter

exporter = TestExporter()
logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[SimpleSpanProcessor(exporter)])

async def homepage(request: Request) -> PlainTextResponse:
    return PlainTextResponse('hello')

app = Starlette(routes=[Route('/hello/{name}', homepage)])
with TestClient(app) as client:
    response = client.get('/hello/world')
assert response.status_code == 200
assert response.text == 'hello'
print(json.dumps(exporter.exported_spans_as_dict()))
"""
    )
    monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
    monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
    # Exercise discovery and dispatch with only Starlette enabled, regardless of other installed integrations.
    excluded = set(OTEL_INSTRUMENTATION_MAP.values()) - {'starlette'}
    if exclude_starlette:
        excluded.add('starlette')
    target = ['-m', 'starlette_app'] if module else [str(script)]
    result = subprocess.run(
        [sys.executable, '-m', 'logfire', 'run', '--summary', '--exclude', ','.join(sorted(excluded)), *target],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    spans = json.loads(result.stdout)
    if exclude_starlette:
        assert spans == []
        assert 'starlette (installed and instrumented)' not in result.stderr
    else:
        # The default CLI configuration keeps the server span and filters send/receive spans.
        assert [span['name'] for span in spans] == ['GET /hello/{name}']
        assert spans[0]['attributes']['http.route'] == '/hello/{name}'
        assert spans[0]['attributes']['http.status_code'] == 200
        assert spans[0]['attributes']['logfire.msg'] == 'GET /hello/world'
        assert 'starlette (installed and instrumented)' in result.stderr


@pytest.mark.parametrize('module', [False, True])
@pytest.mark.parametrize('instrumentation', ['fastapi', 'both', 'excluded', 'explicit', 'excluded-explicit'])
def test_parse_run_fastapi_in_fresh_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: bool, instrumentation: str
) -> None:
    pytest.importorskip('fastapi', reason='FastAPI requires pydantic>=2.7', exc_type=ImportError)
    script = tmp_path / 'fastapi_app.py'
    script.write_text(
        """
import json
import sys

from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import logfire
from logfire.testing import TestExporter

exporter = TestExporter()
logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[SimpleSpanProcessor(exporter)])
app = FastAPI()
if 'explicit' in sys.argv:
    logfire.instrument_fastapi(app)

@app.get('/items/{item_id}')
async def homepage(item_id: int) -> dict[str, int]:
    return {'item_id': item_id}

async def standalone(request: Request) -> PlainTextResponse:
    return PlainTextResponse('hello')

starlette_app = Starlette(routes=[Route('/standalone', standalone)])
with TestClient(app) as client:
    assert client.get('/items/123').json() == {'item_id': 123}
with TestClient(starlette_app) as client:
    assert client.get('/standalone').text == 'hello'
print(json.dumps(exporter.exported_spans_as_dict(parse_json_attributes=True)))
"""
    )
    monkeypatch.setenv('LOGFIRE_SEND_TO_LOGFIRE', 'false')
    monkeypatch.setenv('LOGFIRE_CONSOLE', 'false')
    enabled: set[str] = {'fastapi', 'starlette'} if instrumentation == 'both' else {'fastapi'}
    if instrumentation.startswith('excluded'):
        enabled = set()
    excluded = set(OTEL_INSTRUMENTATION_MAP.values()) - enabled
    target = ['-m', 'fastapi_app'] if module else [str(script)]
    if 'explicit' in instrumentation:
        target.append('explicit')
    result = subprocess.run(
        [sys.executable, '-m', 'logfire', 'run', '--summary', '--exclude', ','.join(sorted(excluded)), *target],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if instrumentation == 'explicit':
        assert result.returncode != 0
        assert (
            'Global FastAPI instrumentation cannot be combined with logfire.instrument_fastapi(app). '
            'Run your application with `logfire run --exclude fastapi ...` to use app-specific instrumentation instead. '
            'If you need both global and app-specific instrumentation, please open an issue at '
            'https://github.com/pydantic/logfire/issues.'
        ) in result.stderr
        return
    assert result.returncode == 0, result.stderr
    spans = json.loads(result.stdout)
    if instrumentation == 'excluded':
        # FastAPI's own native telemetry may remain active, without Logfire's enrichment.
        assert not any('fastapi.arguments.start_timestamp' in span['attributes'] for span in spans)
        assert 'fastapi (installed and instrumented)' not in result.stderr
    else:
        expected = ['GET /items/{item_id}']
        if instrumentation == 'both':
            expected.append('GET /standalone')
        assert [span['name'] for span in spans] == expected
        attributes = spans[0]['attributes']
        assert attributes['fastapi.route.name'] == 'homepage'
        assert attributes['fastapi.arguments.values'] == {'item_id': 123}
        assert attributes['fastapi.arguments.errors'] == []
        for phase in ('arguments', 'endpoint_function'):
            for boundary in ('start_timestamp', 'end_timestamp'):
                assert f'fastapi.{phase}.{boundary}' in attributes
        assert attributes['http.status_code'] == 200
        assert ('fastapi (installed and instrumented)' in result.stderr) == (instrumentation != 'excluded-explicit')


def test_parse_run_script(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', instrument_package_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.OTEL_INSTRUMENTATION_MAP', {'openai': 'openai'})

    main(['run', '--no-summary', run_script_test.__file__, '-x', 'foo'])

    assert configure_mock.call_count == 1
    assert capsys.readouterr().out == 'hi from run_script_test.py\n'
    assert instrument_package_mock.call_args_list == [(('openai',),)]


def test_parse_run_script_with_summary(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', instrument_package_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.OTEL_INSTRUMENTATION_MAP', {'openai': 'openai'})

    main(['run', '--summary', run_script_test.__file__, '-x', 'foo'])

    assert configure_mock.call_count == 1
    out, err = capsys.readouterr()
    assert out == snapshot('hi from run_script_test.py\n')
    assert 'To hide this summary box, use: logfire run --no-summary.' in err
    assert instrument_package_mock.call_args_list == [(('openai',),)]


def test_parse_run_script_relative_path(
    tmp_dir_cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_dir_cwd / 'main.py').write_text('print(__file__, (lambda: 0).__code__.co_filename)')
    monkeypatch.setattr('logfire.configure', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.OTEL_INSTRUMENTATION_MAP', {'openai': 'openai'})

    main(['run', '--no-summary', 'main.py'])

    script_path = os.path.abspath('main.py')
    assert capsys.readouterr().out == f'{script_path} {script_path}\n'


def test_parse_run_module(
    tmp_dir_cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_dir_cwd / 'main.py').write_text(Path(run_script_test.__file__).read_text())
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', instrument_package_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.OTEL_INSTRUMENTATION_MAP', {'openai': 'openai'})

    main(['run', '--no-summary', '-m', 'main', '-x', 'foo'])

    assert configure_mock.call_count == 1
    assert capsys.readouterr().out == snapshot('hi from run_script_test.py\n')
    assert instrument_package_mock.call_args_list == [(('openai',),)]


def test_parse_run_console_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_argv: list[str] = []

    def console_main() -> None:
        seen_argv.extend(sys.argv)

    entry_point = Mock()
    entry_point.load.return_value = console_main
    entry_points = Mock(return_value=[entry_point])
    context = Mock(installed_otel_pkgs=set(), instrument_pkg_map={})
    monkeypatch.setattr('logfire.configure', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.collect_instrumentation_context', Mock(return_value=context))
    monkeypatch.setattr('logfire._internal.cli.run.importlib.metadata.entry_points', entry_points)

    main(['run', '--no-summary', 'demo-cli', '--target-option'])

    assert seen_argv == ['demo-cli', '--target-option']
    entry_points.assert_called_once_with(group='console_scripts', name='demo-cli')
    entry_point.load.assert_called_once_with()


def test_parse_run_console_entry_point_is_loaded_before_working_directory(
    tmp_dir_cwd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_dir = tmp_path / 'installed'
    installed_dir.mkdir()
    marker = tmp_path / 'ran-installed-entry-point'
    module_name = 'shadowed_console_entry_point'
    (installed_dir / f'{module_name}.py').write_text(
        f'from pathlib import Path\ndef main():\n    Path({str(marker)!r}).touch()\n'
    )
    (tmp_dir_cwd / f'{module_name}.py').write_text("def main():\n    raise AssertionError('loaded local module')\n")
    monkeypatch.setattr(sys, 'path', [str(installed_dir), *sys.path])
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    entry_point = importlib.metadata.EntryPoint(name='demo-cli', value=f'{module_name}:main', group='console_scripts')
    context = Mock(installed_otel_pkgs=set(), instrument_pkg_map={})
    monkeypatch.setattr('logfire.configure', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.collect_instrumentation_context', Mock(return_value=context))
    monkeypatch.setattr('logfire._internal.cli.run.importlib.metadata.entry_points', Mock(return_value=[entry_point]))

    main(['run', '--no-summary', 'demo-cli'])

    assert marker.exists()


def test_parse_run_instruments_packages_before_working_directory(
    tmp_dir_cwd: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_dir = tmp_path / 'installed'
    installed_dir.mkdir()
    marker = tmp_path / 'imported-installed-package'
    module_name = 'shadowed_instrumentation_target'
    (installed_dir / f'{module_name}.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    (tmp_dir_cwd / f'{module_name}.py').write_text("raise AssertionError('imported local module')\n")
    # `python -m logfire` puts the working directory first on `sys.path`.
    monkeypatch.setattr(sys, 'path', [str(tmp_dir_cwd), str(installed_dir), *sys.path])
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    context = Mock(installed_otel_pkgs={'opentelemetry-instrumentation-demo'})
    context.instrument_pkg_map = {'opentelemetry-instrumentation-demo': module_name}
    # Give the fake package a Logfire method, so `logfire run` imports it through `instrument_package`.
    monkeypatch.setattr(logfire, f'instrument_{module_name}', Mock(), raising=False)
    monkeypatch.setattr('logfire.configure', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.collect_instrumentation_context', Mock(return_value=context))
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', importlib.import_module)
    monkeypatch.setattr('logfire._internal.cli.run.importlib.metadata.entry_points', Mock(return_value=[]))

    with pytest.raises(FileNotFoundError):
        main(['run', '--no-summary', 'missing-cli'])

    assert marker.exists()


def test_parse_run_console_entry_point_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    entry_point = Mock()
    entry_point.load.return_value = lambda: 17
    context = Mock(installed_otel_pkgs=set(), instrument_pkg_map={})
    monkeypatch.setattr('logfire.configure', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.collect_instrumentation_context', Mock(return_value=context))
    monkeypatch.setattr('logfire._internal.cli.run.importlib.metadata.entry_points', Mock(return_value=[entry_point]))

    with pytest.raises(SystemExit, match='17'):
        main(['run', '--no-summary', 'demo-cli'])


def test_parse_run_console_entry_point_ambiguity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    context = Mock(installed_otel_pkgs=set(), instrument_pkg_map={})
    monkeypatch.setattr('logfire.configure', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.collect_instrumentation_context', Mock(return_value=context))
    monkeypatch.setattr(
        'logfire._internal.cli.run.importlib.metadata.entry_points', Mock(return_value=[Mock(), Mock()])
    )

    with pytest.raises(SystemExit):
        main(['run', '--no-summary', 'demo-cli'])

    assert capsys.readouterr().err == 'Multiple installed packages provide the `demo-cli` console command.\n'


def test_parse_run_unknown_console_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    context = Mock(installed_otel_pkgs=set(), instrument_pkg_map={})
    monkeypatch.setattr('logfire.configure', Mock())
    monkeypatch.setattr('logfire._internal.cli.run.collect_instrumentation_context', Mock(return_value=context))
    monkeypatch.setattr('logfire._internal.cli.run.importlib.metadata.entry_points', Mock(return_value=[]))

    with pytest.raises(FileNotFoundError):
        main(['run', '--no-summary', 'missing-cli'])
