import re
import sys
from datetime import date
from pathlib import Path

import requests

from release.shared import API_PYPROJECT, CHANGELOG_FILE, GITHUB_TOKEN, REPO, ROOT_PYPROJECT, run_command


def update_version(pyproject_file: str, new_version: str) -> None:
    """Update the version in a given pyproject.toml."""
    with open(pyproject_file) as f:
        content = f.read()

    updated_content = re.sub(r'version\s*=\s*"[^\"]+"', f'version = "{new_version}"', content)

    with open(pyproject_file, 'w') as f:
        f.write(updated_content)


def generate_stubs() -> None:
    """Run make logic to generate stubs and update __init__.pyi."""
    run_command('make', 'generate-stubs')


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
    body = re.sub(
        r'https://github.com/pydantic/logfire/pull/(\d+)', r'[#\1](https://github.com/pydantic/logfire/pull/\1)', body
    )
    body = re.sub(r'\*\*Full Changelog.*', '', body, flags=re.DOTALL)
    body = re.sub(r"## What's Changed\n", '', body)

    return body.strip()


def update_history(new_version: str, notes: str) -> None:
    """Update CHANGELOG.md with the new release notes."""
    history_path = Path(CHANGELOG_FILE)
    history_content = history_path.read_text()

    date_today = date.today().strftime('%Y-%m-%d')
    title = f'## [v{new_version}] ({date_today})'
    if title in history_content:
        print(f'WARNING: {title} already exists in CHANGELOG.md')
        sys.exit(1)

    new_chunk = f'{title}\n\n{notes}\n\n'
    updated_content = re.sub(r'(# Release Notes\n\n)', rf'\1{new_chunk}', history_content)
    history_path.write_text(updated_content)

    last_tag = get_last_tag()
    compare_link = f'[v{new_version}]: https://github.com/{REPO}/compare/{last_tag}...v{new_version}\n'
    with open(history_path, 'a') as f:
        f.write(compare_link)


if __name__ == '__main__':
    """Automate the version bump and changelog update process."""

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
