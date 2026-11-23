"""Demonstrate ambiguous source lookup for a relative frame filename.

Run with a Python environment that has ``executing`` installed.
"""

import ast
import os
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FrameType

from executing import Source


def inspect_frame(frame: FrameType, expected_directory: Path, marker: str) -> None:
    """Inspect the trusted fixture's frame after it changes directory."""
    assert Path.cwd() == expected_directory
    assert frame.f_code.co_filename == 'fixture.py'
    assert marker == 'original'

    result = Source.executing(frame)
    source = result.source.text
    node = ast.get_source_segment(source, result.node) if result.node else None

    print(f'frame filename: {frame.f_code.co_filename}')
    print(f'working directory: {Path.cwd()}')
    print(f'running fixture marker: {marker}')
    print(f'recovered source:\n{source}')
    print(f'recovered AST node: {node}')

    assert '"replacement"' in source
    if node is not None:
        assert '"replacement"' in node


def main() -> None:
    """Run the trusted fixture by relative path next to a same-named file."""
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        original = root / 'original'
        replacement = root / 'replacement'
        original.mkdir()
        replacement.mkdir()

        fixture = (
            'import os\n'
            'import sys\n'
            'os.chdir(replacement_directory)\n'
            'inspect_frame(sys._getframe(), replacement_directory, "MARKER")\n'
        )
        (original / 'fixture.py').write_text(fixture.replace('MARKER', 'original'))
        (replacement / 'fixture.py').write_text(fixture.replace('MARKER', 'replacement'))

        previous_directory = Path.cwd()
        try:
            os.chdir(original)
            runpy.run_path(
                'fixture.py',
                init_globals={'inspect_frame': inspect_frame, 'replacement_directory': replacement},
            )
        finally:
            os.chdir(previous_directory)


if __name__ == '__main__':
    main()
