import re

import requests
from packaging.version import Version

from release.shared import CHANGELOG_FILE, REPO, get_github_token, run_command

CHANGELOG_VERSION_RE = re.compile(r'^## \[v([^]]+)\]')


def get_latest_version_from_changelog() -> str:
    """Get the most recently listed version from the changelog."""
    with open(CHANGELOG_FILE) as f:
        for line in f:
            match = CHANGELOG_VERSION_RE.match(line)
            if match:
                version = match.group(1)
                Version(version)
                return version
    raise ValueError('Latest version not found in changelog')


def get_latest_release_notes_from_changelog() -> str:
    """Get the release notes for the latest version from the changelog."""
    with open(CHANGELOG_FILE) as f:
        for line in f:
            match = CHANGELOG_VERSION_RE.match(line)
            if match:
                Version(match.group(1))
                break
        else:
            raise ValueError('Latest version not found in changelog')

        release_notes: list[str] = []
        for line in f:
            if line.startswith('## [v'):
                break
            release_notes.append(line)
    return ''.join(release_notes)


def create_github_release_draft(version: str, release_notes: str):
    """Create a GitHub release draft."""
    url = f'https://api.github.com/repos/{REPO}/releases'
    headers = {'Authorization': f'token {get_github_token()}'}
    data = {
        'tag_name': f'v{version}',
        'name': f'v{version}',
        'body': release_notes,
        'draft': True,
        'prerelease': Version(version).is_prerelease,
    }
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    release_url = response.json()['html_url']
    # Publishing happens in the edit page
    edit_url = release_url.replace('/releases/tag/', '/releases/edit/')
    return edit_url


def commit_and_push_changes(version: str) -> None:
    """Commit and push changes to a new branch."""
    branch_name = f'release/v{version}'
    run_command('git', 'checkout', '-b', branch_name)
    run_command('git', 'add', '.')
    run_command('git', 'commit', '-m', f'Bump version to v{version}')
    run_command('git', 'push', 'origin', branch_name)


def open_pull_request(version: str):
    """Open a pull request on GitHub."""
    url = f'https://api.github.com/repos/{REPO}/pulls'
    headers = {'Authorization': f'token {get_github_token()}'}
    data = {
        'title': f'Release v{version}',
        'head': f'release/v{version}',
        'base': 'main',
        'body': f'Bumping version to v{version}.',
    }
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()['html_url']


if __name__ == '__main__':
    """Automate the release draft + PR creation process."""

    version = get_latest_version_from_changelog()
    release_notes = get_latest_release_notes_from_changelog()

    commit_and_push_changes(version)
    pr_url = open_pull_request(version)
    print(f'Opened PR: {pr_url}')

    draft_url = create_github_release_draft(version, release_notes)
    print(f'Release draft created: {draft_url}')

    print(f'SUCCESS: Completed release process for v{version}')
