import re
from pathlib import Path, PurePosixPath

from scripts.build_offline_skill_prompt import (
    MANDATORY_REFERENCES,
    PUBLIC_SKILLS_ROOT,
    SKILL_ORDER,
    SKILLS_ROOT,
    _qualify_reference_headings,  # pyright: ignore[reportPrivateUsage]
    _reference_anchor,  # pyright: ignore[reportPrivateUsage]
    _reference_section_anchor,  # pyright: ignore[reportPrivateUsage]
    _rewrite_public_links_for_offline_bundle,  # pyright: ignore[reportPrivateUsage]
    build,
)

REPO_ROOT = Path(__file__).parent.parent
CHECKED_IN_BUNDLE = SKILLS_ROOT / 'logfire-setup-offline.md'

# Matches a markdown link whose target is a `references/...` path, relative either to the
# skill it's written in (`./references/...`) or to a sibling skill
# (`../logfire-instrumentation/references/...`), with an optional `#fragment`. Doesn't match
# plain skill-name pointers ("the `logfire-infrastructure` skill"), which resolve to a
# `# Skill: ...` heading instead.
#
# The cross-skill prefix and the same-skill `./` prefix are alternatives, not a required
# sequence -- an earlier version chained them (`(?:\.\./[a-z0-9-]+/)?\./?references/...`),
# which made a literal `.` mandatory right before `references/` and so never matched a
# cross-skill link at all (nothing follows `../logfire-x/` but `references/` directly).
REFERENCE_LINK = re.compile(r'\[[^\]]+\]\((\.\.?/[^)#\s]+\.md)(?:#[^)\s]*)?\)')


def _appendix_headings(bundle: str) -> set[str]:
    """Every `## path/to/file.md` heading under `# Reference Files`."""
    if '# Reference Files' not in bundle:
        return set()
    appendix = bundle.split('# Reference Files', 1)[1]
    return {m.group(1) for m in re.finditer(r'^## (.+\.md)$', appendix, re.MULTILINE)}


def test_mandatory_references_are_never_dropped() -> None:
    """The compact (`--no-references`) build must still inline MANDATORY_REFERENCES.

    Every skill's Step 1 links to the shared auth reference. Omitting it entirely (the
    original behavior of `--no-references`) left that link pointing at nothing in the one
    artifact whose whole point is "works with no fetching" -- the most safety-critical
    reference in the bundle, unreachable.
    """
    # An empty MANDATORY_REFERENCES would make the loop below vacuously pass -- guard the
    # guard, since that's the same "no config found scores as passing" shape this repo's
    # own CI treats as a real defect elsewhere.
    assert MANDATORY_REFERENCES, 'MANDATORY_REFERENCES is empty; nothing for this test to check'
    compact = build(include_references=False)
    headings = _appendix_headings(compact)
    for mandatory in MANDATORY_REFERENCES:
        assert mandatory in headings, f'{mandatory} missing from the compact build appendix'


def test_full_build_has_no_dead_reference_links() -> None:
    """Every `references/...` link in the full build resolves to an appendix entry.

    A link surviving a skill-body edit while the appendix entry it points at gets renamed,
    moved, or (per the bug above) omitted is exactly the failure mode that produced a dead
    auth link in every skill body -- this catches it independent of which reference broke.
    """
    full = build(include_references=True)
    headings = _appendix_headings(full)
    assert headings, 'full build produced no Reference Files appendix at all'
    assert '[credential handoff instructions](#if-the-calling-skill-needs-a-write-token-not-just-a-cli-session)' in full

    assert not REFERENCE_LINK.findall(full), 'full build left filesystem-relative reference links unresolved'

    for heading in headings:
        assert f'<a id="{_reference_anchor(heading)}"></a>' in full
    anchors = [_reference_anchor(heading) for heading in headings]
    assert len(anchors) == len(set(anchors)), 'reference paths produced colliding appendix anchors'
    for anchor in re.findall(r'\]\(#(reference-[^)]+)\)', full):
        assert f'<a id="{anchor}"></a>' in full, f'generated link has no target: {anchor}'
    all_anchors = re.findall(r'<a id="([^"]+)"></a>', full)
    assert len(all_anchors) == len(set(all_anchors)), 'generated appendix anchors are not unique'


def test_reference_links_inside_appendix_resolve_to_inlined_anchors() -> None:
    """Sibling and parent-relative links must not escape the flattened offline bundle."""
    references = frozenset(
        {
            'logfire-instrumentation/references/auth.md',
            'logfire-instrumentation/references/javascript/ai-sdk.md',
            'logfire-instrumentation/references/javascript/node-runtime.md',
        }
    )
    source = '[Node](./node-runtime.md) and [auth](../auth.md)'

    rewritten = _rewrite_public_links_for_offline_bundle(
        source,
        source_path=PurePosixPath('logfire-instrumentation/references/javascript/ai-sdk.md'),
        bundled_references=references,
    )

    assert rewritten == (
        '[Node](#reference-logfire-instrumentation-references-javascript-node-runtime-md) and '
        '[auth](#reference-logfire-instrumentation-references-auth-md)'
    )


def test_reference_link_fragments_are_qualified_by_their_file() -> None:
    """A section link must not collide with an earlier heading in the flat bundle."""
    reference = 'logfire-instrumentation/references/python/logging-patterns.md'
    rewritten = _rewrite_public_links_for_offline_bundle(
        '[metrics](./references/python/logging-patterns.md#custom-metrics)',
        source_path=PurePosixPath('logfire-instrumentation/SKILL.md'),
        bundled_references=frozenset({reference}),
    )

    anchor = _reference_section_anchor(reference, '#custom-metrics')
    assert rewritten == f'[metrics](#{anchor})'
    assert f'<a id="{anchor}"></a>' in build(include_references=True)


def test_reference_heading_aliases_do_not_rewrite_code_fences() -> None:
    """Shell comments and similar code must not become anchors in generated examples."""
    source = '# Real heading\n\n```sh\n```python\n# not a heading\n```\n'
    qualified = _qualify_reference_headings(source, 'skill/references/example.md')

    assert qualified.endswith('```sh\n```python\n# not a heading\n```\n')
    assert qualified.count('<a id=') == 1


def test_build_rewrites_public_links_only_for_inlined_skills() -> None:
    compact = build(include_references=False)

    for skill in SKILL_ORDER:
        assert f'{PUBLIC_SKILLS_ROOT}/{skill}/' not in compact
    for skill in ('logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals'):
        assert f'](#skill-{skill})' in compact
    assert f'{PUBLIC_SKILLS_ROOT}/logfire-query/SKILL.md' in compact
    assert f'{PUBLIC_SKILLS_ROOT}/logfire-ui/SKILL.md' in compact


def test_auth_link_rewrite_preserves_the_complete_fragment() -> None:
    source = f'[Auth]({PUBLIC_SKILLS_ROOT}/logfire-instrumentation/references/auth.md#write_token.v1)'

    assert _rewrite_public_links_for_offline_bundle(source) == '[Auth](#write_token.v1)'


def test_inlined_skill_links_resolve_in_generated_and_checked_in_bundles() -> None:
    """Every synthetic skill fragment has the heading that creates its anchor."""
    checked_in = CHECKED_IN_BUNDLE.read_text(encoding='utf-8')
    for bundle in (build(include_references=False), checked_in):
        for skill in ('logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals'):
            assert f'](#skill-{skill})' in bundle
            assert f'# Skill: {skill}\n' in bundle


def test_checked_in_bundle_matches_a_fresh_build() -> None:
    """The committed logfire-setup-offline.md is `--no-references` output, regenerated.

    Every source-skill edit in this session needed a manual `python3
    scripts/build_offline_skill_prompt.py --no-references -o ...` afterward, purely by
    convention -- nothing enforced it. This fails loudly the next time someone forgets.
    """
    assert CHECKED_IN_BUNDLE.is_file(), f'{CHECKED_IN_BUNDLE} does not exist'
    fresh = build(include_references=False)
    checked_in = CHECKED_IN_BUNDLE.read_text(encoding='utf-8')
    assert checked_in == fresh, (
        f'{CHECKED_IN_BUNDLE} is stale -- regenerate with '
        f'`python3 scripts/build_offline_skill_prompt.py --no-references -o '
        f'{CHECKED_IN_BUNDLE.relative_to(REPO_ROOT)}`'
    )


def test_compact_bundle_stays_under_a_token_budget() -> None:
    """A regression guard, not a design target -- content should grow because something
    genuinely needed adding, not because nobody noticed it creeping. ~16.5k tokens (chars/4)
    leaves real headroom over the bundle's current size without being loose enough to miss
    a real regression (e.g. `--no-references` quietly stopping omitting anything). The
    hardened, isolation-pinned CLI forms in auth guidance (~400 chars each) and the
    repository-credential safety checks pushed the compact build over the old 15k budget.
    """
    compact = build(include_references=False)
    estimated_tokens = len(compact) // 4
    assert estimated_tokens < 16_500, (
        f'compact bundle is ~{estimated_tokens} estimated tokens -- '
        f'either this is intentional growth (raise this budget) or `--no-references` '
        f'stopped omitting the deep-dive reference files it is meant to skip'
    )
