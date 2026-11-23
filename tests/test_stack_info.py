from pathlib import Path

import pytest

from logfire._internal import stack_info


def test_non_user_path_requires_directory_boundary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    library = tmp_path / 'library'
    monkeypatch.setattr(stack_info, 'NON_USER_CODE_PREFIXES', (str(library),))

    assert stack_info.is_non_user_path(library / 'module.py')
    assert not stack_info.is_non_user_path(tmp_path / 'library-extra' / 'app.py')


def test_add_non_user_code_prefix_applies_to_code_already_inspected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(stack_info, 'NON_USER_CODE_PREFIXES', ())
    stack_info.is_user_code.cache_clear()
    try:
        library = tmp_path / 'library'
        code = compile('', str(library / 'module.py'), 'exec')

        assert stack_info.is_user_code(code)

        stack_info.add_non_user_code_prefix(library)

        assert not stack_info.is_user_code(code)
    finally:
        stack_info.is_user_code.cache_clear()
