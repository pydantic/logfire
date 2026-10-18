"""Keep the hosted-dataset skill general purpose and its credentials boundaries intact."""

import re
from pathlib import Path
from urllib.parse import urlsplit

SKILL_DIR = Path(__file__).resolve().parents[1] / 'logfire-sdk/logfire/.agents/skills/logfire-datasets'
SKILL_PATH = SKILL_DIR / 'SKILL.md'
DOCUMENTS = sorted(SKILL_DIR.rglob('*.md'))


def _text(path: Path) -> str:
    return ' '.join(path.read_text().split())


def test_datasets_skill_links_resolve_or_use_the_public_catalog() -> None:
    links = [
        (document, match.group(1))
        for document in DOCUMENTS
        for match in re.finditer(r'\]\(([^)\s]+)\)', document.read_text())
    ]
    assert links
    for document, target in links:
        parsed = urlsplit(target)
        if not parsed.scheme:
            assert (document.parent / parsed.path).is_file(), (document, target)
        elif parsed.path.startswith('/.well-known/agent-skills/'):
            assert parsed.scheme == 'https'
            assert parsed.netloc == 'pydantic.dev'


def test_datasets_skill_separates_the_api_key_from_the_read_token() -> None:
    skill = _text(SKILL_PATH)
    assert 'LOGFIRE_API_KEY' in skill
    assert 'LOGFIRE_READ_TOKEN' in skill
    assert 'project:read_datasets' in skill
    assert 'project:write_datasets' in skill
    assert '401 Invalid read token' in skill
    assert 'logfire-instrumentation/references/auth.md' in skill


def test_datasets_skill_keeps_secrets_out_of_output_and_tracked_files() -> None:
    skill = _text(SKILL_PATH)
    assert 'never print or log it' in skill
    assert 'never write it into a tracked file' in skill
    assert 'git check-ignore -q .env' in skill
    assert 'printf \'LOGFIRE_READ_TOKEN=%s\\n\' "$token" >> .env' in skill
    assert 'Do not use `--save`' in skill


def test_datasets_skill_guards_writes_to_shared_projects() -> None:
    skill = _text(SKILL_PATH)
    assert 'get explicit confirmation before pushing' in skill
    assert 'project_id' in skill
    assert 'create the dataset only if it is missing' in skill


def test_datasets_skill_assumes_no_particular_trace_format() -> None:
    """Span names and attribute keys vary by instrumentation; the skill must discover them."""
    for document in DOCUMENTS:
        text = document.read_text()
        for instrumentation_specific in ('gen_ai.', 'pydantic_ai.', 'invoke_agent', 'final_result'):
            assert instrumentation_specific not in text, (document.name, instrumentation_specific)
