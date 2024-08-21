from dirty_equals import IsPartialDict

from logfire import VERSION
from logfire._internal.collect_system_info import collect_package_info


def test_collect_package_info() -> None:
    assert collect_package_info() == IsPartialDict({'logfire': VERSION})
