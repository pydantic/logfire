import subprocess


def run_command(*args: str) -> str:
    """Run a shell command and return the output."""
    try:
        p = subprocess.run(args, capture_output=True, check=True, encoding='utf-8')
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f'Error running command: {" ".join(args)} with error: {e.stderr}')
    return p.stdout.strip()


REPO = 'pydantic/logfire'
CHANGELOG_FILE = 'CHANGELOG.md'
ROOT_PYPROJECT = 'pyproject.toml'
API_PYPROJECT = 'logfire-api/pyproject.toml'
GITHUB_TOKEN = run_command('gh', 'auth', 'token')
