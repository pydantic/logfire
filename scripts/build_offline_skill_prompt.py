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
import posixpath
import re
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / 'logfire' / '.agents' / 'skills'
PUBLIC_SKILLS_ROOT = 'https://pydantic.dev/.well-known/agent-skills'
AUTH_REFERENCE_PATH = 'logfire-instrumentation/references/auth.md'
AUTH_REFERENCE_ANCHOR = '#authenticate-and-select-the-exact-project'

# Hub first, then the three it routes to, in the order a reader would want
# to meet them: detect/install first, the two optional add-ons after.
SKILL_ORDER = [
    'logfire-setup',
    'logfire-instrumentation',
    'logfire-infrastructure',
    'logfire-evals',
]

# Every skill body links to this one, by relative path, from its very first
# step -- it is not an optional deep-dive, it is the auth command sequence
# every skill's Step 1 depends on. `--no-references` is meant to cut the
# language-specific deep dives (roughly half the bundle's size), not leave
# the one reference every skill needs unreachable: a `--no-references` build
# used to keep the "[Authenticate...](.../references/auth.md)" links from
# every skill while omitting the file they point at, so the one artifact
# whose whole point is "works with no fetching" sent a reader straight into
# a dead link for the most safety-critical reference in the bundle.
MANDATORY_REFERENCES = [
    'logfire-instrumentation/references/auth.md',
]
RELATIVE_MARKDOWN_LINK = re.compile(
    r'(?P<prefix>\]\()(?P<target>\.\.?/[^)#\s]+\.md)(?P<fragment>#[^)\s]+)?(?P<suffix>\))'
)
MARKDOWN_HEADING = re.compile(r'^(?P<marks>#{1,6})\s+(?P<title>.+)$')
MARKDOWN_FENCE = re.compile(r'^(?P<marker>`{3,}|~{3,})')


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


def _reference_anchor(relative: str) -> str:
    """Return the stable HTML anchor for one inlined reference file."""
    slug = re.sub(r'[^a-z0-9]+', '-', relative.lower()).strip('-')
    return f'reference-{slug}'


def _reference_section_anchor(relative: str, fragment: str) -> str:
    """Qualify a source heading fragment with its inlined reference file."""
    return f'{_reference_anchor(relative)}--{fragment.removeprefix("#")}'


def _markdown_heading_slug(title: str) -> str:
    """Approximate GitHub's Markdown heading fragment for reference source headings."""
    without_links = re.sub(r'\[([^]]+)]\([^)]+\)', r'\1', title)
    return ''.join(
        character for character in without_links.casefold() if character.isalnum() or character in ' _-'
    ).replace(' ', '-')


def _qualify_reference_headings(text: str, relative: str) -> str:
    """Add collision-free aliases for headings inside one flattened reference file."""
    occurrences: dict[str, int] = {}
    fence: tuple[str, int] | None = None
    rendered: list[str] = []
    for line in text.splitlines(keepends=True):
        fence_match = MARKDOWN_FENCE.match(line.lstrip())
        if fence_match:
            marker = fence_match.group('marker')
            if fence is None:
                fence = marker[0], len(marker)
            elif marker[0] == fence[0] and len(marker) >= fence[1] and not line.lstrip()[len(marker) :].strip():
                fence = None
        elif fence is None and (heading := MARKDOWN_HEADING.fullmatch(line.rstrip('\r\n'))):
            slug = _markdown_heading_slug(heading.group('title'))
            occurrence = occurrences.get(slug, 0)
            occurrences[slug] = occurrence + 1
            fragment = slug if occurrence == 0 else f'{slug}-{occurrence}'
            anchor = _reference_section_anchor(relative, fragment)
            rendered.append(f'<a id="{anchor}"></a>\n\n')
        rendered.append(line)
    return ''.join(rendered)


def _rewrite_public_links_for_offline_bundle(
    text: str,
    *,
    source_path: PurePosixPath | None = None,
    bundled_references: frozenset[str] = frozenset(),
) -> str:
    """Point links to bundled skills and references at their inlined sections."""
    auth_sources = (
        f'{PUBLIC_SKILLS_ROOT}/{AUTH_REFERENCE_PATH}',
        f'../{AUTH_REFERENCE_PATH}',
        AUTH_REFERENCE_PATH,
        './references/auth.md',
    )
    for source in auth_sources:
        text = re.sub(
            rf'{re.escape(source)}(#[^)\s]+)?',
            lambda match: match.group(1) or AUTH_REFERENCE_ANCHOR,
            text,
        )
    for name in SKILL_ORDER:
        text = text.replace(f'{PUBLIC_SKILLS_ROOT}/{name}/SKILL.md', f'#skill-{name}')
        text = text.replace(f'{PUBLIC_SKILLS_ROOT}/{name}/', f'../{name}/')

    if source_path is not None:

        def replace_relative_link(match: re.Match[str]) -> str:
            target = match.group('target')
            resolved = posixpath.normpath((source_path.parent / target).as_posix())
            if resolved not in bundled_references:
                return match.group(0)
            fragment = match.group('fragment')
            destination = (
                f'#{_reference_section_anchor(resolved, fragment)}' if fragment else f'#{_reference_anchor(resolved)}'
            )
            return f'{match.group("prefix")}{destination}{match.group("suffix")}'

        text = RELATIVE_MARKDOWN_LINK.sub(replace_relative_link, text)
    return text


def _render_skill(name: str, *, bundled_references: frozenset[str]) -> str:
    skill_dir = SKILLS_ROOT / name
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.is_file():
        raise BuildOfflinePromptError(f'{skill_md} does not exist')
    description, body = _strip_frontmatter(skill_md.read_text(encoding='utf-8'))
    section = [f'# Skill: {name}', '']
    if description:
        section += [f'*{description}*', '']
    section.append(
        _rewrite_public_links_for_offline_bundle(
            body,
            source_path=PurePosixPath(name) / 'SKILL.md',
            bundled_references=bundled_references,
        )
    )
    return '\n'.join(section)


def _render_appendix(name: str, *, bundled_references: frozenset[str]) -> str:
    skill_dir = SKILLS_ROOT / name
    parts: list[str] = []
    for ref in _reference_files(skill_dir):
        relative = ref.relative_to(SKILLS_ROOT)
        relative_path = relative.as_posix()
        if relative_path not in bundled_references:
            continue
        content = _rewrite_public_links_for_offline_bundle(
            ref.read_text(encoding='utf-8').strip(),
            source_path=PurePosixPath(relative_path),
            bundled_references=bundled_references,
        )
        content = _qualify_reference_headings(content, relative_path)
        parts.append(f'<a id="{_reference_anchor(relative_path)}"></a>\n\n## {relative}\n\n{content}')
    return '\n\n'.join(parts)


def _preamble(*, include_references: bool) -> str:
    references_note = ' Authentication links jump directly to the inlined authentication appendix.'
    references_note += (
        ' Links to the other bundled reference files jump to their inlined entries in the '
        '**Reference Files** appendix at the end.'
        if include_references
        else ' This build omits the other `./references/...` deep-dive files (language-specific '
        'edge cases) to stay shorter; if one turns out to matter, fetch it directly from the repo.'
    )
    return (
        '# Pydantic Logfire — Offline Setup Prompt\n\n'
        'This is a self-contained bundle of the `logfire-setup` hub skill and every skill it\n'
        'routes to (`logfire-instrumentation`, `logfire-infrastructure`,\n'
        '`logfire-evals`), for use when you cannot fetch URLs. Read top to bottom;\n'
        'nothing below needs a network fetch to resolve.\n\n'
        'A pointer to "the `logfire-infrastructure` skill" (or any other skill named\n'
        'above) means the section below headed `# Skill: logfire-infrastructure` --\n'
        f'read it in place of fetching it.{references_note}\n'
    )


def build(*, include_references: bool = True) -> str:
    """Concatenate every skill in `SKILL_ORDER`, optionally with their reference files.

    Even when `include_references` is False, MANDATORY_REFERENCES are still inlined --
    see that constant for why omitting them isn't just "shorter", it's a dead link.
    """
    bundled_references = frozenset(
        ref.relative_to(SKILLS_ROOT).as_posix()
        for name in SKILL_ORDER
        for ref in _reference_files(SKILLS_ROOT / name)
        if include_references or ref.relative_to(SKILLS_ROOT).as_posix() in MANDATORY_REFERENCES
    )
    skill_sections = [_render_skill(name, bundled_references=bundled_references) for name in SKILL_ORDER]
    parts = [_preamble(include_references=include_references), *skill_sections]
    appendix_sections = [
        rendered for name in SKILL_ORDER if (rendered := _render_appendix(name, bundled_references=bundled_references))
    ]
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
        help=(
            'skill bodies only -- skip the deep-dive reference-file appendix (roughly half the '
            'size), except the mandatory auth reference every skill depends on, which is always '
            'kept'
        ),
    )
    args = parser.parse_args()

    prompt = build(include_references=not args.no_references)
    word_count = len(prompt.split())
    print(
        f'{word_count} words, {len(prompt)} chars (~{len(prompt) // 4} tokens by the usual chars/4 estimate)',
        file=sys.stderr,
    )

    if args.output:
        args.output.write_text(prompt, encoding='utf-8')
        print(f'wrote {args.output}', file=sys.stderr)
    else:
        sys.stdout.write(prompt)


if __name__ == '__main__':
    main()
