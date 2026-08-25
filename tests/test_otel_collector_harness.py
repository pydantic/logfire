from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from tests.otel_collector.conftest import CollectorHarness, collector_harness


def test_collector_setup_failure_removes_generated_private_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifacts_dir = tmp_path / 'artifacts'
    commands: list[list[str]] = []

    class TempPathFactory:
        def mktemp(self, basename: str) -> Path:
            assert basename == 'otel-collector-artifacts'
            return artifacts_dir

    def run(command: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[0] == 'openssl':
            Path(command[command.index('-keyout') + 1]).write_text('private key')
            return subprocess.CompletedProcess(command, 1, '', 'certificate generation failed')
        assert command[:2] in (['docker', 'logs'], ['docker', 'rm'])
        return subprocess.CompletedProcess(command, 1 if command[1] == 'logs' else 0, '', '')

    def which(executable: str) -> str:
        return f'/usr/bin/{executable}'

    monkeypatch.setattr('shutil.which', which)
    monkeypatch.setattr('subprocess.run', run)

    fixture = cast(
        Callable[[pytest.TempPathFactory], Iterator[CollectorHarness]], getattr(collector_harness, '__wrapped__')
    )
    generator = fixture(cast(pytest.TempPathFactory, TempPathFactory()))
    with pytest.raises(pytest.fail.Exception, match='failed to generate Collector certificate'):
        next(generator)

    assert not (artifacts_dir / 'key.pem').exists()
    assert (artifacts_dir / 'captured-otlp.json').exists()
    assert any(command[:3] == ['docker', 'rm', '--force'] for command in commands)
