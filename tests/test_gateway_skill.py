"""Keep application Gateway setup independent from CLI authentication."""

import re
from pathlib import Path
from urllib.parse import urlsplit

SKILL_PATH = Path(__file__).resolve().parents[1] / 'logfire-sdk/logfire/.agents/skills/logfire-gateway/SKILL.md'


def test_gateway_skill_delegates_cli_credentials_without_requiring_them() -> None:
    skill = SKILL_PATH.read_text()
    assert 'references/application-gateway.md' in skill
    assert 'api-key gateway' not in skill
    assert 'init use' not in skill
    assert 'Gateway Connect flow' in skill
    assert "Agent('gateway/openai:gpt-5.2')" in skill
    assert 'PYDANTIC_AI_GATEWAY_API_KEY' in skill


def test_gateway_skill_cross_repository_links_use_the_public_catalog() -> None:
    links = [match.group(1) for match in re.finditer(r'\]\(([^)]+)\)', SKILL_PATH.read_text())]
    assert links
    for target in links:
        parsed = urlsplit(target)
        if not parsed.scheme:
            assert (SKILL_PATH.parent / parsed.path).is_file(), target
        elif 'logfire-coding-agents' in parsed.path:
            assert parsed.scheme == 'https'
            assert parsed.netloc == 'pydantic.dev'
            assert parsed.path.startswith('/.well-known/agent-skills/logfire-coding-agents/')


def test_gateway_skill_preserves_secret_destination_and_verification_boundaries() -> None:
    skill = ' '.join(SKILL_PATH.read_text().split())
    assert 'write the file atomically' in skill
    assert 'Never stage or commit the secret-bearing file or key' in skill
    assert 'PYDANTIC_AI_GATEWAY_BASE_URL' in skill
    assert 'LOGFIRE_GATEWAY_API_KEY' in skill
    assert 'small synthetic payload' in skill
    assert 'may incur usage charges' in skill
