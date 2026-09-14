from pathlib import Path

import pytest

from logfire._internal import stack_info


def test_non_user_path_requires_directory_boundary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    library = tmp_path / 'library'
    monkeypatch.setattr(stack_info, 'NON_USER_CODE_PREFIXES', (str(library),))

    assert stack_info.is_non_user_path(library / 'module.py')
    assert not stack_info.is_non_user_path(tmp_path / 'library-extra' / 'app.py')
