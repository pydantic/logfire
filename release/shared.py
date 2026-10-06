import subprocess


def run_command(*args: str) -> str:
    """Run a shell command and return the output."""
    p = subprocess.run(args, stdout=subprocess.PIPE, check=True, encoding='utf-8')
    return p.stdout.strip()


REPO = 'pydantic/logfire'
CHANGELOG_FILE = 'CHANGELOG.md'
SDK_PYPROJECT = 'logfire-sdk/pyproject.toml'
META_PYPROJECT = 'logfire/pyproject.toml'
API_PYPROJECT = 'logfire-api/pyproject.toml'


def get_github_token() -> str:
    """Read the GitHub token only when a release operation needs it."""
    return run_command('gh', 'auth', 'token')
