"""Exercise the changelog workflow's actual shell validation."""

import os
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.mark.parametrize(
    ('before', 'after', 'changed', 'changelog', 'exit_code'),
    [
        ('6.0.0b8', '5.2.0', 'false', '## [v5.2.0] (2026-10-13)\n', 0),
        ('5.2.0', '5.3.0', 'false', '## [v5.2.0] (2026-10-13)\n', 1),
        ('5.2.0', '5.3.0', 'true', '## [v5.3.0] (2026-10-21)\n', 0),
        ('5.2.0', '5.2.0', 'false', '', 0),
        ('6.0.0b8', '5.2.0', 'false', '## [v5.2.0b1] (2026-10-13)\n', 1),
        ('6.0.0b8', '5.2.0', 'false', '[v5.2.0]: https://example.com/compare\n', 1),
    ],
)
def test_changelog_workflow(
    tmp_path: Path, before: str, after: str, changed: str, changelog: str, exit_code: int
) -> None:
    workflow = (Path(__file__).parents[1] / '.github/workflows/check_changelog.yml').read_text()
    step = workflow.split('      - name: Verify version change and CHANGELOG.md update\n', 1)[1]
    script = dedent(step.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])
    # Supply versions directly so this tests the workflow's validation without
    # needing a Git repository or modifying package metadata.
    validation = 'if [ "$VERSION_BEFORE"' + script.split('if [ "$VERSION_BEFORE"', 1)[1]
    (tmp_path / 'CHANGELOG.md').write_text(changelog)
    result = subprocess.run(
        ['bash', '-eu', '-c', validation],
        cwd=tmp_path,
        env={**os.environ, 'VERSION_BEFORE': before, 'VERSION_AFTER': after, 'changelog_changed': changed},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
