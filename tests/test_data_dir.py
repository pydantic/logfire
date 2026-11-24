from pathlib import Path

from logfire._internal.utils import ensure_data_dir_exists


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
