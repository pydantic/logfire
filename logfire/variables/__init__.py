from importlib.util import find_spec

if not find_spec('pydantic'):
    raise RuntimeError(
        'The `logfire.variables` module requires the `pydantic` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[variables]'"
    )
