from __future__ import annotations

import importlib.metadata
import shutil
from pathlib import Path

import pytest

from logfire.cli import main


@pytest.mark.parametrize('has_uv', [True, False])
@pytest.mark.parametrize(
    ('installed', 'requirements'),
    [
        (['requests'], ["'logfire[requests]'"]),
        (['pymysql'], ['opentelemetry-instrumentation-pymysql']),
        (['requests', 'pymysql'], ["'logfire[requests]'", 'opentelemetry-instrumentation-pymysql']),
        (['psycopg'], ["'logfire[psycopg,psycopg2]'"]),
        (['psycopg', 'opentelemetry-instrumentation-psycopg'], ["'logfire[psycopg2]'"]),
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
    assert commands == [f'{installer} {requirement}' for requirement in requirements]
