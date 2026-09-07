from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path


class _DocsServeError(RuntimeError):
    pass


def _run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ''


def _pnpm_command() -> str:
    return 'pnpm.cmd' if os.name == 'nt' else 'pnpm'


def _checkout_path(logfire_root: Path, environment: Mapping[str, str]) -> Path:
    if override := environment.get('UNIFIED_DOCS_PATH'):
        return Path(override).expanduser().resolve()

    sibling = logfire_root.parent / 'unified-docs'
    if sibling.is_dir():
        return sibling.resolve()

    raise _DocsServeError(
        'Local preview requires access to pydantic/unified-docs. '
        'Set UNIFIED_DOCS_PATH to an existing checkout; external contributors should request '
        'a hosted preview with the trigger:docs pull-request label.'
    )


def _validate_checkout(checkout: Path) -> None:
    required = [checkout / 'package.json', checkout / 'scripts' / 'docs-dev.mjs']
    missing = [path.relative_to(checkout) for path in required if not path.is_file()]
    if missing:
        missing_list = ', '.join(map(str, missing))
        raise _DocsServeError(f'{checkout} is not a usable unified-docs checkout (missing {missing_list})')


def _check_node_version() -> None:
    version = _run(['node', '--version'], capture=True).removeprefix('v')
    if version.split('.', 1)[0] != '24':
        raise _DocsServeError(f'Node.js 24 is required to preview the docs (current: {version})')


def _dependencies_missing(checkout: Path) -> bool:
    astro = 'astro.cmd' if os.name == 'nt' else 'astro'
    python = (
        checkout / '.venv' / 'Scripts' / 'python.exe' if os.name == 'nt' else checkout / '.venv' / 'bin' / 'python3'
    )
    return not (checkout / 'node_modules' / '.bin' / astro).is_file() or not python.is_file()


def _prepare_dependencies(checkout: Path) -> None:
    if not _dependencies_missing(checkout):
        return

    print('Preparing unified-docs dependencies...')
    _run([_pnpm_command(), 'install', '--frozen-lockfile'], cwd=checkout)
    _run(['uv', 'sync'], cwd=checkout)


def _launch(checkout: Path, logfire_root: Path, environment: Mapping[str, str]) -> None:
    command = [
        _pnpm_command(),
        'docs:dev',
        '--library',
        'logfire',
        '--source',
        str(logfire_root),
    ]
    if port := environment.get('DOCS_PORT'):
        command.extend(['--', '--port', port])
    _run(command, cwd=checkout)


def _main(environment: Mapping[str, str] = os.environ) -> int:
    logfire_root = Path(__file__).resolve().parents[1]
    checkout = _checkout_path(logfire_root, environment)
    _validate_checkout(checkout)
    _check_node_version()
    _prepare_dependencies(checkout)
    _launch(checkout, logfire_root, environment)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(_main())
    except _DocsServeError as error:
        raise SystemExit(str(error)) from error
    except FileNotFoundError as error:
        command = error.filename or 'required command'
        raise SystemExit(f'{command} is required to preview the docs') from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
    except KeyboardInterrupt:
        raise SystemExit(130) from None
