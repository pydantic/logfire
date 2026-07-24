from __future__ import annotations

# pyright: reportPrivateUsage=false
import os
from pathlib import Path

import pytest

from scripts import docs_serve


def _make_checkout(path: Path) -> None:
    (path / 'scripts').mkdir(parents=True)
    (path / 'package.json').write_text('{}')
    (path / 'scripts' / 'docs-dev.mjs').write_text('')


def test_checkout_path_prefers_explicit_override(tmp_path: Path) -> None:
    checkout = docs_serve._checkout_path(
        tmp_path / 'logfire',
        {
            'UNIFIED_DOCS_PATH': str(tmp_path / 'custom'),
        },
    )

    assert checkout == tmp_path / 'custom'


def test_checkout_path_discovers_sibling(tmp_path: Path) -> None:
    logfire_root = tmp_path / 'logfire'
    sibling = tmp_path / 'unified-docs'
    logfire_root.mkdir()
    sibling.mkdir()

    assert docs_serve._checkout_path(logfire_root, {}) == sibling


def test_checkout_path_explains_private_preview_requirement(tmp_path: Path) -> None:
    with pytest.raises(docs_serve._DocsServeError, match='requires access.*UNIFIED_DOCS_PATH'):
        docs_serve._checkout_path(tmp_path / 'logfire', {})


def test_validate_checkout_rejects_missing_unified_docs_files(tmp_path: Path) -> None:
    checkout = tmp_path / 'unified-docs'
    checkout.mkdir()

    with pytest.raises(docs_serve._DocsServeError, match=r'missing package\.json, scripts/docs-dev\.mjs'):
        docs_serve._validate_checkout(checkout)


def test_dependencies_are_prepared_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = tmp_path / 'unified-docs'
    _make_checkout(checkout)
    calls: list[tuple[list[str], Path | None]] = []

    def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
        calls.append((command, cwd))
        return ''

    monkeypatch.setattr(docs_serve, '_run', run)
    monkeypatch.setattr(docs_serve, '_pnpm_command', lambda: 'pnpm')

    docs_serve._prepare_dependencies(checkout)

    assert calls == [
        (['pnpm', 'install', '--frozen-lockfile'], checkout),
        (['uv', 'sync'], checkout),
    ]


def test_checkout_is_not_reinstalled_when_dependencies_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = tmp_path / 'unified-docs'
    _make_checkout(checkout)
    astro = 'astro.cmd' if os.name == 'nt' else 'astro'
    python = (
        checkout / '.venv' / 'Scripts' / 'python.exe' if os.name == 'nt' else checkout / '.venv' / 'bin' / 'python3'
    )
    (checkout / 'node_modules' / '.bin').mkdir(parents=True)
    (checkout / 'node_modules' / '.bin' / astro).write_text('')
    python.parent.mkdir(parents=True)
    python.write_text('')
    calls: list[list[str]] = []

    def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
        calls.append(command)
        return 'local-head'

    monkeypatch.setattr(docs_serve, '_run', run)
    docs_serve._prepare_dependencies(checkout)

    assert calls == []


def test_launch_passes_absolute_logfire_source_and_optional_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / 'unified-docs'
    logfire_root = tmp_path / 'logfire'
    calls: list[tuple[list[str], Path | None]] = []

    def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
        calls.append((command, cwd))
        return ''

    monkeypatch.setattr(docs_serve, '_run', run)
    monkeypatch.setattr(docs_serve, '_pnpm_command', lambda: 'pnpm')

    docs_serve._launch(checkout, logfire_root, {'DOCS_PORT': '4322'})

    assert calls == [
        (
            [
                'pnpm',
                'docs:dev',
                '--library',
                'logfire',
                '--source',
                str(logfire_root),
                '--',
                '--port',
                '4322',
            ],
            checkout,
        )
    ]


def test_wrong_node_version_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
        return '22.0.0'

    monkeypatch.setattr(docs_serve, '_run', run)

    with pytest.raises(docs_serve._DocsServeError, match='Node.js 24.*22.0.0'):
        docs_serve._check_node_version()
