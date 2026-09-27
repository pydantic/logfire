"""Helpers for keeping the released distributions on one version."""

import re
from pathlib import Path


def replace_project_version(content: str, path: Path, new_version: str) -> str:
    """Return TOML with its single PEP 621 project version replaced."""
    lines = content.splitlines(keepends=True)
    try:
        project_start = next(index for index, line in enumerate(lines) if line.strip() == '[project]') + 1
    except StopIteration:
        raise ValueError(f'Could not find one project version in {path}') from None
    project_end = next(
        (index for index in range(project_start, len(lines)) if lines[index].lstrip().startswith('[')),
        len(lines),
    )
    version_lines = [index for index in range(project_start, project_end) if re.match(r'^\s*version\s*=', lines[index])]
    if len(version_lines) != 1:
        raise ValueError(f'Could not find one project version in {path}')
    version_line = version_lines[0]
    lines[version_line], count = re.subn(
        r'^(\s*version\s*=\s*)"[^"]+"',
        rf'\g<1>"{new_version}"',
        lines[version_line],
        count=1,
    )
    if count != 1:
        raise ValueError(f'Could not find one project version in {path}')
    return ''.join(lines)


def update_project_version(pyproject_file: str | Path, new_version: str) -> None:
    """Update the single PEP 621 project version in a `pyproject.toml`."""
    path = Path(pyproject_file)
    updated = replace_project_version(path.read_text(), path, new_version)
    path.write_text(updated)


def update_meta_version(pyproject_file: str | Path, new_version: str) -> None:
    """Update the meta-package version and every exact SDK dependency."""
    path = Path(pyproject_file)
    content = replace_project_version(path.read_text(), path, new_version)
    updated, count = re.subn(
        r'(logfire-sdk(?:\[[^]]+\])?==)[^";\s]+',
        rf'\g<1>{new_version}',
        content,
    )
    if count == 0:
        raise ValueError(f'Could not find an exact logfire-sdk dependency in {path}')
    path.write_text(updated)
