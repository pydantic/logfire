"""Test editor tooling against both copies in the migration-safe SDK wheel."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import jedi

CONSUMER = """\
from typing import assert_type

import logfire

client = logfire.configure(send_to_logfire=False)
assert_type(client, logfire.Logfire)
client.info('typed consumer', answer=42)
"""


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    """Run a command and return its output with useful failure diagnostics."""
    print(f'+ {subprocess.list2cmdline(command)}', flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    return result.stdout


def venv_python(venv: Path) -> Path:
    """Return the platform-specific Python executable in a virtual environment."""
    return venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def site_packages(python: Path, *, cwd: Path, env: dict[str, str]) -> Path:
    """Ask the target interpreter for its pure-Python installation directory."""
    output = run(
        [
            str(python),
            '-c',
            'import json, sysconfig; print(json.dumps(sysconfig.get_path("purelib")))',
        ],
        cwd=cwd,
        env=env,
    )
    return Path(json.loads(output)).resolve()


def send_message(process: subprocess.Popen[bytes], message: dict[str, Any]) -> None:
    """Send one JSON-RPC message to a language server."""
    assert process.stdin is not None
    payload = json.dumps(message).encode()
    process.stdin.write(f'Content-Length: {len(payload)}\r\n\r\n'.encode() + payload)
    process.stdin.flush()


def receive_message(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    """Receive one JSON-RPC message from a language server."""
    assert process.stdout is not None
    headers: dict[str, str] = {}
    while line := process.stdout.readline():
        if line == b'\r\n':
            break
        key, value = line.decode().split(':', 1)
        headers[key.lower()] = value.strip()
    if 'content-length' not in headers:
        raise AssertionError(f'Language server exited before responding (exit code {process.poll()})')
    return json.loads(process.stdout.read(int(headers['content-length'])))


def wait_for_response(process: subprocess.Popen[bytes], request_id: int) -> Any:
    """Wait for a response, acknowledging any requests sent by the server first."""
    while True:
        message = receive_message(process)
        if message.get('id') == request_id:
            if error := message.get('error'):
                raise AssertionError(f'Language server request failed: {error}')
            return message.get('result')
        if 'id' in message and 'method' in message:
            send_message(process, {'jsonrpc': '2.0', 'id': message['id'], 'result': None})


def uri_path(uri: str) -> Path:
    """Convert a file URI returned by the language server into a local path."""
    parsed = urlparse(uri)
    if parsed.scheme != 'file':
        raise AssertionError(f'Expected a file URI, got {uri!r}')
    return Path(url2pathname(unquote(parsed.path))).resolve()


def pyright_definition(
    language_server: Path, python: Path, work_dir: Path, consumer: Path, env: dict[str, str]
) -> Path:
    """Ask Pyright's language server to navigate to ``logfire.Logfire``."""
    process = subprocess.Popen(
        [str(language_server), '--stdio'],
        cwd=work_dir,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        send_message(
            process,
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'initialize',
                'params': {
                    'processId': None,
                    'rootUri': work_dir.as_uri(),
                    'capabilities': {},
                    'workspaceFolders': [{'uri': work_dir.as_uri(), 'name': work_dir.name}],
                },
            },
        )
        wait_for_response(process, 1)
        send_message(process, {'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
        send_message(
            process,
            {
                'jsonrpc': '2.0',
                'method': 'workspace/didChangeConfiguration',
                'params': {'settings': {'python': {'pythonPath': str(python)}}},
            },
        )
        send_message(
            process,
            {
                'jsonrpc': '2.0',
                'method': 'textDocument/didOpen',
                'params': {
                    'textDocument': {
                        'uri': consumer.as_uri(),
                        'languageId': 'python',
                        'version': 1,
                        'text': CONSUMER,
                    }
                },
            },
        )
        send_message(
            process,
            {
                'jsonrpc': '2.0',
                'id': 2,
                'method': 'textDocument/definition',
                'params': {
                    'textDocument': {'uri': consumer.as_uri()},
                    'position': {'line': 5, 'character': 32},
                },
            },
        )
        definitions = wait_for_response(process, 2)
        if not definitions:
            raise AssertionError('Pyright returned no definition for logfire.Logfire')
        location = definitions[0] if isinstance(definitions, list) else definitions
        definition_uri = location.get('uri', location.get('targetUri'))
        if not isinstance(definition_uri, str):
            raise AssertionError(f'Pyright returned an invalid definition: {location!r}')

        send_message(process, {'jsonrpc': '2.0', 'id': 3, 'method': 'shutdown', 'params': None})
        wait_for_response(process, 3)
        send_message(process, {'jsonrpc': '2.0', 'method': 'exit', 'params': None})
        if process.wait(timeout=10) != 0:
            raise AssertionError(f'Pyright language server exited with {process.returncode}')
        return uri_path(definition_uri)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def jedi_definition(work_dir: Path, venv: Path, consumer: Path) -> Path:
    """Ask Jedi to navigate to ``logfire.Logfire``."""
    project = jedi.Project(work_dir, environment_path=venv)
    definitions = jedi.Script(path=consumer, project=project).goto(
        6, 34, follow_imports=True, follow_builtin_imports=True
    )
    matches = [definition for definition in definitions if definition.full_name == 'logfire._internal.main.Logfire']
    if len(matches) != 1 or matches[0].module_path is None:
        raise AssertionError(f'Jedi returned unexpected definitions: {definitions!r}')
    return matches[0].module_path.resolve()


def assert_tooling(
    *,
    expected_package: Path,
    work_dir: Path,
    venv: Path,
    python: Path,
    consumer: Path,
    env: dict[str, str],
) -> None:
    """Check runtime and editor resolution for one installed-package layout."""
    expected_init = expected_package / '__init__.py'
    imported_from = Path(
        run(
            [str(python), '-c', 'import logfire; print(logfire.__file__)'],
            cwd=work_dir,
            env=env,
        ).strip()
    ).resolve()
    if imported_from != expected_init:
        raise AssertionError(f'Python imported {imported_from}, expected {expected_init}')

    pyright = shutil.which('pyright')
    language_server = shutil.which('pyright-langserver')
    mypy = shutil.which('mypy')
    if pyright is None or language_server is None or mypy is None:
        raise AssertionError('pyright, pyright-langserver, and mypy must be installed')

    run([pyright, '--pythonpath', str(python), str(consumer)], cwd=work_dir, env=env)
    run(
        [mypy, '--no-incremental', '--strict', '--python-executable', str(python), str(consumer)],
        cwd=work_dir,
        env=env,
    )

    expected_definition = expected_package / '_internal/main.py'
    actual_pyright_definition = pyright_definition(Path(language_server), python, work_dir, consumer, env)
    if actual_pyright_definition != expected_definition:
        raise AssertionError(f'Pyright navigated to {actual_pyright_definition}, expected {expected_definition}')
    actual_jedi_definition = jedi_definition(work_dir, venv, consumer)
    if actual_jedi_definition != expected_definition:
        raise AssertionError(f'Jedi navigated to {actual_jedi_definition}, expected {expected_definition}')


def main() -> None:
    """Install the SDK wheel, then test its normal and fallback package copies."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel', type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise AssertionError(f'SDK wheel does not exist: {wheel}')

    uv = shutil.which('uv')
    if uv is None:
        raise AssertionError('uv is required to run the editor tooling test')
    for variable in ('PYTHONPATH', 'VIRTUAL_ENV'):
        os.environ.pop(variable, None)
    env = os.environ.copy()

    with tempfile.TemporaryDirectory(prefix='logfire-editor-tooling-') as temp_dir:
        work_dir = Path(temp_dir).resolve()
        venv = work_dir / 'venv'
        python = venv_python(venv)
        run([uv, 'venv', '--python', sys.executable, str(venv)], cwd=work_dir, env=env)
        run([uv, 'pip', 'install', '--python', str(python), str(wheel)], cwd=work_dir, env=env)

        consumer = work_dir / 'consumer.py'
        consumer.write_text(CONSUMER)
        (work_dir / 'pyrightconfig.json').write_text(
            json.dumps({'typeCheckingMode': 'strict', 'venvPath': '.', 'venv': venv.name})
        )

        packages = site_packages(python, cwd=work_dir, env=env)
        normal_package = packages / 'logfire'
        fallback_package = packages / '_logfire_sdk/logfire'
        assert_tooling(
            expected_package=normal_package,
            work_dir=work_dir,
            venv=venv,
            python=python,
            consumer=consumer,
            env=env,
        )

        saved_package = work_dir / 'normal-logfire-package'
        normal_package.rename(saved_package)
        try:
            assert_tooling(
                expected_package=fallback_package,
                work_dir=work_dir,
                venv=venv,
                python=python,
                consumer=consumer,
                env=env,
            )
        finally:
            saved_package.rename(normal_package)


if __name__ == '__main__':
    main()
