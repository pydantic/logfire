"""Tests for creating stable and prerelease release drafts."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from release import push


def test_get_latest_prerelease_from_changelog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text(
        '# Release Notes\n\n## [v6.0.0b1] (2026-09-15)\n\nBeta notes.\n\n## [v5.1.0] (2026-08-28)\n\nStable notes.\n'
    )
    monkeypatch.setattr(push, 'CHANGELOG_FILE', changelog)

    assert push.get_latest_version_from_changelog() == '6.0.0b1'
    assert push.get_latest_release_notes_from_changelog() == '\nBeta notes.\n\n'


@pytest.mark.parametrize(('version', 'prerelease'), [('6.0.0b1', True), ('6.0.0', False)])
def test_create_github_release_draft_marks_prereleases(
    version: str, prerelease: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = Mock()
    response.json.return_value = {'html_url': f'https://github.com/pydantic/logfire/releases/tag/v{version}'}
    post = Mock(return_value=response)
    monkeypatch.setattr(push, 'get_github_token', lambda: 'token')
    monkeypatch.setattr(push.requests, 'post', post)

    assert push.create_github_release_draft(version, 'Release notes') == (
        f'https://github.com/pydantic/logfire/releases/edit/v{version}'
    )
    post.assert_called_once_with(
        'https://api.github.com/repos/pydantic/logfire/releases',
        json={
            'tag_name': f'v{version}',
            'name': f'v{version}',
            'body': 'Release notes',
            'draft': True,
            'prerelease': prerelease,
        },
        headers={'Authorization': 'token token'},
    )
    response.raise_for_status.assert_called_once_with()
