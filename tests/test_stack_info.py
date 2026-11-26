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
    stack_info._is_user_code.cache_clear()  # pyright: ignore[reportPrivateUsage]
    try:
        library = tmp_path / 'library'
        code = compile('', str(library / 'module.py'), 'exec')

        assert stack_info.is_user_code(code)

        stack_info.add_non_user_code_prefix(library)

        assert not stack_info.is_user_code(code)
    finally:
        stack_info._is_user_code.cache_clear()  # pyright: ignore[reportPrivateUsage]


def test_code_objects_differing_only_in_filename_are_cached_separately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    library_file = str(tmp_path / 'library' / 'helper.py')
    user_file = str(tmp_path / 'app' / 'helper.py')
    monkeypatch.setattr(stack_info, 'NON_USER_CODE_PREFIXES', (str(tmp_path / 'library'),))
    source = 'def helper():\n    return 1\n'
    library_code = compile(source, library_file, 'exec')
    user_code = compile(source, user_file, 'exec')
    # CPython ignores co_filename when comparing and hashing code objects.
    assert library_code == user_code

    assert not stack_info.is_user_code(library_code)
    assert stack_info.is_user_code(user_code)
    library_info = stack_info.get_code_object_info(library_code)
    user_info = stack_info.get_code_object_info(user_code)
    assert library_info == {**stack_info.get_filepath_attribute(library_file), 'code.lineno': 1}
    assert user_info == {**stack_info.get_filepath_attribute(user_file), 'code.lineno': 1}
