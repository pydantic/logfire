"""Exercise real package-manager upgrades from monolithic to split Logfire."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    """Run a command with enough output to diagnose CI failures."""
    print(f'+ {subprocess.list2cmdline(command)}', flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def find_one(dist: Path, pattern: str) -> Path:
    """Find exactly one wheel matching a distribution-specific pattern."""
    wheels = list(dist.glob(pattern))
    if len(wheels) != 1:
        raise AssertionError(f'Expected one wheel matching {pattern!r}, found {wheels!r}')
    return wheels[0]


def wheel_version(wheel: Path) -> str:
    """Read a wheel's version from its core metadata."""
    with zipfile.ZipFile(wheel) as archive:
        metadata_files = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
        if len(metadata_files) != 1:
            raise AssertionError(f'Expected one METADATA file in {wheel}, found {metadata_files!r}')
        message = BytesParser().parsebytes(archive.read(metadata_files[0]))
    version = message['Version']
    if version is None:
        raise AssertionError(f'{wheel} has no Version metadata')
    return version


def venv_python(venv: Path) -> Path:
    """Return the platform-specific Python executable in a virtual environment."""
    return venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def venv_script(venv: Path, name: str) -> Path:
    """Return a platform-specific console-script path."""
    filename = f'{name}.exe' if os.name == 'nt' else name
    return venv / ('Scripts' if os.name == 'nt' else 'bin') / filename


class Installer:
    """Run equivalent package operations through pip or uv."""

    def __init__(self, name: str, python: Path, cwd: Path, env: dict[str, str], find_links: Path) -> None:
        self.name = name
        self.python = python
        self.cwd = cwd
        self.env = env
        self.find_links = find_links
        uv = shutil.which('uv')
        if uv is None:
            raise AssertionError('uv is required to run the upgrade test')
        self.uv = uv

    def install(self, *requirements: str, upgrade: bool = False, force: bool = False, no_deps: bool = False) -> None:
        """Install requirements with the selected installer."""
        options = ['--find-links', str(self.find_links)]
        if upgrade:
            options.append('--upgrade')
        if force:
            options.append('--force-reinstall')
        if no_deps:
            options.append('--no-deps')

        if self.name == 'pip':
            command = [str(self.python), '-m', 'pip', 'install', *options, *requirements]
        else:
            command = [self.uv, 'pip', 'install', '--python', str(self.python), *options, *requirements]
        run(command, cwd=self.cwd, env=self.env)

    def uninstall(self, *distributions: str) -> None:
        """Uninstall distributions with the selected installer."""
        if self.name == 'pip':
            command = [str(self.python), '-m', 'pip', 'uninstall', '--yes', *distributions]
        else:
            command = [self.uv, 'pip', 'uninstall', '--python', str(self.python), *distributions]
        run(command, cwd=self.cwd, env=self.env)

    def check(self) -> None:
        """Validate that every installed distribution has its dependencies."""
        if self.name == 'pip':
            command = [str(self.python), '-m', 'pip', 'check']
        else:
            command = [self.uv, 'pip', 'check', '--python', str(self.python)]
        run(command, cwd=self.cwd, env=self.env)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--installer', choices=('pip', 'uv'), required=True)
    parser.add_argument('--from-version', required=True)
    parser.add_argument('--dist', type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Run the complete upgrade, removal, and restoration lifecycle."""
    args = parse_args()
    dist = args.dist.resolve()
    smoke_test = Path(__file__).with_name('upgrade_install_smoke.py').resolve()
    meta_wheel = find_one(dist, 'logfire-[0-9]*-py3-none-any.whl')
    sdk_wheel = find_one(dist, 'logfire_sdk-[0-9]*-py3-none-any.whl')
    target_version = wheel_version(meta_wheel)
    if wheel_version(sdk_wheel) != target_version:
        raise AssertionError('The logfire and logfire-sdk wheels have different versions')

    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env.pop('VIRTUAL_ENV', None)

    with tempfile.TemporaryDirectory(prefix='logfire-upgrade-') as temp_dir:
        work_dir = Path(temp_dir).resolve()
        venv = work_dir / 'venv'
        uv = shutil.which('uv')
        if uv is None:
            raise AssertionError('uv is required to create the test environment')
        run([uv, 'venv', '--python', sys.executable, '--seed', str(venv)], cwd=work_dir, env=env)

        python = venv_python(venv)
        cli = venv_script(venv, 'logfire')
        standalone_cli = venv_script(venv, 'logfire-cli')
        installer = Installer(args.installer, python, work_dir, env, dist)

        def assert_state(state: str, version: str) -> None:
            run([str(python), str(smoke_test), state, version], cwd=work_dir, env=env)
            installer.check()

        installer.install(f'logfire=={args.from_version}')
        assert_state('legacy', args.from_version)
        run([str(cli), '--version'], cwd=work_dir, env=env)

        # Installing through an extra-bearing direct URL exercises both local
        # wheel resolution and the meta-package's forwarding of SDK extras.
        installer.install(f'logfire[sqlite3] @ {meta_wheel.as_uri()}', upgrade=True)
        assert_state('split', target_version)
        run([str(cli), '--version'], cwd=work_dir, env=env)

        # Reinstalling both wheels catches RECORD/file-ownership regressions that
        # are hidden by a one-way upgrade test.
        installer.install(str(sdk_wheel), str(meta_wheel), force=True, no_deps=True)
        assert_state('split', target_version)
        run([str(cli), '--version'], cwd=work_dir, env=env)
        run([str(standalone_cli), '--version'], cwd=work_dir, env=env)

        # The compatibility distribution owns no Python package, so removing it
        # must leave a working SDK. It owns the `logfire` launcher, so that goes
        # with it while logfire-cli keeps its own `logfire-cli` launcher.
        installer.uninstall('logfire')
        assert_state('sdk-and-cli', target_version)
        if cli.exists():
            raise AssertionError(f'The logfire launcher survived uninstalling logfire: {cli}')
        run([str(standalone_cli), '--version'], cwd=work_dir, env=env)
        installer.uninstall('logfire-cli')
        assert_state('sdk-only', target_version)
        if standalone_cli.exists():
            raise AssertionError(f'The CLI launcher survived uninstalling logfire-cli: {standalone_cli}')

        installer.install(str(meta_wheel))
        assert_state('split', target_version)
        run([str(cli), '--version'], cwd=work_dir, env=env)


if __name__ == '__main__':
    main()
