"""Concatenate the Logfire skills into one self-contained offline prompt.

The skills are designed to be fetched individually and on demand -- a hub
skill points at `logfire-instrumentation` by name, and each of those points
at `./references/*.md` files alongside it. That's the right shape for an
agent with live URL access. It's the wrong shape for a "copy this prompt"
button aimed at an agent that can't fetch anything: every "see the
logfire-infrastructure skill" or "see ./references/collector/..." becomes a
dead pointer.

This script produces the other artifact: one markdown file with everything
inlined, so a pointer like "the logfire-infrastructure skill" can be read as
"the section below headed accordingly" instead of a fetch that will fail.

Usage:
    uv run --no-project python scripts/build_offline_skill_prompt.py [-o OUTPUT]

Prints a word/char count to stderr either way; writes to OUTPUT (default
stdout) so callers can pipe it, diff it against a checked-in copy, or wire it
into a build step without this script knowing which.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / 'logfire' / '.agents' / 'skills'

# Hub first, then the three it routes to, in the order a reader would want
# to meet them: detect/install first, the two optional add-ons after.
SKILL_ORDER = [
    'logfire',
    'logfire-instrumentation',
    'logfire-infrastructure',
    'logfire-evals',
]


class BuildOfflinePromptError(RuntimeError):
    """A skill file was missing or malformed."""


def _strip_frontmatter(text: str) -> tuple[str, str]:
    """Split a SKILL.md into (description, body). The body keeps its own `#` title."""
    if not text.startswith('---\n'):
        raise BuildOfflinePromptError('SKILL.md is missing its frontmatter block')
    end = text.find('\n---\n', 4)
    if end == -1:
        raise BuildOfflinePromptError('SKILL.md frontmatter is not closed with a second `---`')
    frontmatter, body = text[4:end], text[end + 5 :]
    description = ''
    for line in frontmatter.splitlines():
        if line.startswith('description:'):
            description = line[len('description:') :].strip()
            break
    return description, body.strip('\n')


def _reference_files(skill_dir: Path) -> list[Path]:
    references_dir = skill_dir / 'references'
    if not references_dir.is_dir():
        return []
    return sorted(references_dir.rglob('*.md'))


def _render_skill(name: str) -> str:
    skill_dir = SKILLS_ROOT / name
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.is_file():
        raise BuildOfflinePromptError(f'{skill_md} does not exist')
    description, body = _strip_frontmatter(skill_md.read_text())
    section = [f'# Skill: {name}', '']
    if description:
        section += [f'*{description}*', '']
    section.append(body)
    return '\n'.join(section)


def _render_appendix(name: str) -> str:
    skill_dir = SKILLS_ROOT / name
    parts: list[str] = []
    for ref in _reference_files(skill_dir):
        relative = ref.relative_to(SKILLS_ROOT)
        parts.append(f'## {relative}\n\n{ref.read_text().strip()}')
    return '\n\n'.join(parts)


def _preamble(*, include_references: bool) -> str:
    references_note = (
        ' A pointer to a file under `./references/...` means the matching entry in the '
        '**Reference Files** appendix at the end, headed with that same path.'
        if include_references
        else ' This build omits the `./references/...` deep-dive files (language-specific '
        'edge cases) to stay shorter -- if a pointer to one of those turns out to matter, '
        'fetch it directly from the repo instead.'
    )
    return (
        '# Pydantic Logfire — Offline Setup Prompt\n\n'
        'This is a self-contained bundle of the `logfire` hub skill and every skill it\n'
        'routes to (`logfire-instrumentation`, `logfire-infrastructure`,\n'
        '`logfire-evals`), for use when you cannot fetch URLs. Read top to bottom;\n'
        'nothing below needs a network fetch to resolve.\n\n'
        'A pointer to "the `logfire-infrastructure` skill" (or any other skill named\n'
        'above) means the section below headed `# Skill: logfire-infrastructure` --\n'
        f'read it in place of fetching it.{references_note}\n'
    )


def build(*, include_references: bool = True) -> str:
    """Concatenate every skill in `SKILL_ORDER`, optionally with their reference files."""
    skill_sections = [_render_skill(name) for name in SKILL_ORDER]
    parts = [_preamble(include_references=include_references), *skill_sections]
    if include_references:
        appendix_sections = [rendered for name in SKILL_ORDER if (rendered := _render_appendix(name))]
        if appendix_sections:
            parts.append('# Reference Files\n\n' + '\n\n---\n\n'.join(appendix_sections))
    return '\n\n---\n\n'.join(parts) + '\n'


def main() -> None:
    """CLI entry point: build the prompt and write it to `--output` or stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-o', '--output', type=Path, default=None, help='write to this path instead of stdout')
    parser.add_argument(
        '--no-references',
        action='store_true',
        help='skill bodies only -- skip the reference-file appendix (roughly half the size)',
    )
    args = parser.parse_args()

    prompt = build(include_references=not args.no_references)
    word_count = len(prompt.split())
    print(
        f'{word_count} words, {len(prompt)} chars (~{len(prompt) // 4} tokens by the usual chars/4 estimate)',
        file=sys.stderr,
    )

    if args.output:
        args.output.write_text(prompt)
        print(f'wrote {args.output}', file=sys.stderr)
    else:
        print(prompt)


if __name__ == '__main__':
    main()
