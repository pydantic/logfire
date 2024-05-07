import re
from pathlib import Path

logfire_pyproject = Path('pyproject.toml')
noop_pyproject = Path('logfire-noop/pyproject.toml')

version_re = re.compile(r'version = "(?P<version>.*)"')


def get_version(pyproject: Path) -> str:
    with pyproject.open() as f:
        for line in f.readlines():
            match = version_re.match(line)
            if match:
                return match.group('version')

    raise ValueError('Version not found')


logfire_version = get_version(logfire_pyproject)
noop_version = get_version(noop_pyproject)

print(f'Logfire version: {logfire_version}')
print(f'Logfire-noop version: {noop_version}')


def rewrite_pyproject(pyproject: Path, version: str) -> None:
    with pyproject.open() as f:
        lines = f.readlines()

    with pyproject.open('w') as f:
        for line in lines:
            f.write(version_re.sub(f'version = "{version}"', line))


if logfire_version != noop_version:
    rewrite_pyproject(noop_pyproject, logfire_version)
    print('Updated logfire-noop version')
