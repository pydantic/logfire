import subprocess


def run_command(*args: str) -> str:
    """Run a shell command and return the output."""
    p = subprocess.run(args, stdout=subprocess.PIPE, check=True, encoding='utf-8')
    return p.stdout.strip()


REPO = 'pydantic/logfire'
CHANGELOG_FILE = 'CHANGELOG.md'
ROOT_PYPROJECT = 'pyproject.toml'
API_PYPROJECT = 'logfire-api/pyproject.toml'


def get_github_token() -> str:
    """Read the GitHub token only when a release operation needs it."""
    return run_command('gh', 'auth', 'token')
