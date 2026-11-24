from pathlib import Path

import pytest

from logfire._internal.utils import ensure_data_dir_exists


@pytest.mark.parametrize('has_credentials', [False, True])
def test_logfire_directory_is_gitignored(tmp_path: Path, has_credentials: bool) -> None:
    data_dir = tmp_path / '.logfire'
    if has_credentials:
        data_dir.mkdir()
        (data_dir / 'logfire_credentials.json').write_text('{}')

    ensure_data_dir_exists(data_dir)

    assert (data_dir / '.gitignore').read_text() == '*'


def test_existing_gitignore_is_preserved(tmp_path: Path) -> None:
    data_dir = tmp_path / '.logfire'
    data_dir.mkdir()
    gitignore = data_dir / '.gitignore'
    gitignore.write_text('custom rule\n')

    ensure_data_dir_exists(data_dir)

    assert gitignore.read_text() == 'custom rule\n'


def test_foreign_directory_contents_are_not_ignored(tmp_path: Path) -> None:
    data_dir = tmp_path / 'custom'
    data_dir.mkdir()
    (data_dir / 'my-file.txt').write_text('keep')

    ensure_data_dir_exists(data_dir)

    assert not (data_dir / '.gitignore').exists()
