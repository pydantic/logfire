from typing import Any

# Installing the package `inline-snapshot` in CI causes errors until this is fixed:
# https://github.com/15r10nk/inline-snapshot/issues/54
# So for now you need to `pip install inline-snapshot` locally if you want to use
# e.g. `pytest --inline-snapshot=fix`.
try:
    from inline_snapshot import snapshot
except ImportError:
    # For just running tests, this is enough.
    def snapshot(x: Any) -> Any:
        return x
