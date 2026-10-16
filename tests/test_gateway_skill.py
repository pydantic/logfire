"""Keep application Gateway setup independent from CLI authentication."""

from pathlib import Path


def test_gateway_skill_delegates_cli_credentials_without_requiring_them() -> None:
    skill = (
        Path(__file__).resolve().parents[1] / 'logfire-sdk/logfire/.agents/skills/logfire-gateway/SKILL.md'
    ).read_text()
    assert 'references/application-gateway.md' in skill
    assert 'api-key gateway' not in skill
    assert 'init use' not in skill
    assert 'Gateway Connect flow' in skill
    assert "Agent('gateway/openai:gpt-5.2')" in skill
    assert 'PYDANTIC_AI_GATEWAY_API_KEY' in skill
