import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import requests
import toml


def run_command(*args: str) -> str:
    """Run a shell command and return the output."""
    p = subprocess.run(args, stdout=subprocess.PIPE, check=True, encoding='utf-8')
    return p.stdout.strip()


REPO = 'pydantic/logfire'
CHANGELOG_FILE = 'CHANGELOG.md'
ROOT_PYPROJECT = 'pyproject.toml'
API_PYPROJECT = 'logfire-api/pyproject.toml'
GITHUB_TOKEN = run_command('gh', 'auth', 'token')


def update_version(pyproject_file: str, new_version: str) -> None:
    """Update the version in a given pyproject.toml."""
    config = toml.load(pyproject_file)
    config['project']['version'] = new_version
    with open(pyproject_file, 'w') as f:
        toml.dump(config, f)


def generate_stubs() -> None:
    """Run make logic to generate stubs and update __init__.pyi."""
    run_command('make', 'run', 'generate-stubs')


def get_last_tag() -> str:
    """Get the latest tag from the Git repository."""
    return run_command('git', 'describe', '--tags', '--abbrev=0')


def get_notes(new_version: str) -> str:
    """Generate release notes from GitHub's release notes generator."""
    last_tag = get_last_tag()

    data = {
        'target_committish': 'main',
        'previous_tag_name': last_tag,
        'tag_name': f'v{new_version}',
    }

    response = requests.post(
        f'https://api.github.com/repos/{REPO}/releases/generate-notes',
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {GITHUB_TOKEN}',
        },
        json=data,
    )
    response.raise_for_status()
    body = response.json()['body']

    # Clean up the release notes
    body = re.sub(r'<!--.*?-->\n\n', '', body)
    body = re.sub(r'([^\n])(\n#+ .+?\n)', r'\1\n\2', body)  # Add blank line before headers
    body = re.sub(r'https://github.com/pydantic/logfire/pull/(\d+)', r'[#\1](\0)', body)
    body = re.sub(r'\*\*Full Changelog\*\*: .*\n?', '', body)

    return body.strip()


def update_history(new_version: str, notes: str) -> None:
    """Update CHANGELOG.md with the new release notes."""
    history_path = Path(CHANGELOG_FILE)
    history_content = history_path.read_text()

    date_today = date.today().strftime('%Y-%m-%d')
    title = f'## v{new_version} ({date_today})'
    if title in history_content:
        print(f'WARNING: {title} already exists in CHANGELOG.md')
        sys.exit(1)

    new_chunk = f'{title}\n\n{notes}\n\n'
    history_path.write_text(new_chunk + history_content)

    # Add a comparison link at the end of the file
    last_tag = get_last_tag()
    compare_link = f'[v{new_version}]: https://github.com/{REPO}/compare/{last_tag}...v{new_version}\n'
    with open(history_path, 'a') as f:
        f.write(compare_link)


def create_github_release_draft(version: str, release_notes: str):
    """Create a GitHub release draft."""
    url = f'https://api.github.com/repos/{REPO}/releases'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    data = {
        'tag_name': f'v{version}',
        'name': f'v{version}',
        'body': release_notes,
        'draft': True,
        'prerelease': False,
    }
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()['html_url']


def commit_and_push_changes(version: str) -> None:
    """Commit and push changes to a new branch."""
    branch_name = f'release/v{version}'
    run_command('git', 'checkout', '-b', branch_name)
    run_command('git', 'add', '.')
    run_command('git', 'commit', '-m', f"'Bump version to v{version}'")
    run_command('git', 'push', 'origin', branch_name)


def open_pull_request(version: str):
    """Open a pull request on GitHub."""
    url = f'https://api.github.com/repos/{REPO}/pulls'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    data = {
        'title': f'Release v{version}',
        'head': f'release/v{version}',
        'base': 'main',
        'body': f'Bumping version to v{version}.',
    }
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()['html_url']


def create_github_release(new_version: str, notes: str):
    """Create a new release on GitHub."""
    url = f'https://api.github.com/repos/{REPO}/releases'

    data = {
        'tag_name': f'v{new_version}',
        'name': f'v{new_version}',
        'body': notes,
        'draft': True,
    }

    response = requests.post(
        url,
        headers={
            'Authorization': f'Bearer {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github+json',
        },
        json=data,
    )
    response.raise_for_status()


def main():
    """Automate the release process."""
    if len(sys.argv) != 2:
        print('Usage: python release.py {VERSION}')
        sys.exit(1)

    version = sys.argv[1]

    update_version(ROOT_PYPROJECT, version)
    update_version(API_PYPROJECT, version)
    print(f'Updated version to v{version} in both pyproject.toml files.')

    generate_stubs()
    print('Generated stubs.')

    release_notes = get_notes(version)
    update_history(version, release_notes)
    print('Release notes added to CHANGELOG.md.')

    commit_and_push_changes(version)
    pr_url = open_pull_request(version)
    print(f'Opened PR: {pr_url}')

    draft_url = create_github_release_draft(version, release_notes)
    print(f'Release draft created: {draft_url}')

    print(f'SUCCESS: Completed release process for v{version}')


if __name__ == '__main__':
    main()
