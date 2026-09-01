from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def extract_agent_setup_prompt(path: Path, component: str) -> str:
    content = path.read_text(encoding='utf-8')
    opening_tag = f'<{component}>'
    closing_tag = f'</{component}>'
    assert content.count(opening_tag) == 1
    assert content.count(closing_tag) == 1

    component_content = content.split(opening_tag, 1)[1].split(closing_tag, 1)[0]
    lines = component_content.strip().splitlines()
    opening_fence = lines[0]
    assert opening_fence.endswith('text')
    fence = opening_fence.removesuffix('text')
    assert len(fence) >= 3 and set(fence) == {'`'}
    assert lines[-1] == fence

    # If the prompt embeds its own code fence (it doesn't, currently -- this is a short
    # prompt with no code block of its own), the outer fence must outrun it, or the inner
    # fence closes the outer block early.
    embedded_fence_lengths = [len(line) - len(line.lstrip('`')) for line in lines[1:-1] if line.startswith('`')]
    if embedded_fence_lengths:
        assert len(fence) > max(embedded_fence_lengths)

    prompt = '\n'.join(lines[1:-1])
    assert prompt
    return prompt


def test_agent_setup_prompts_match() -> None:
    index_prompt = extract_agent_setup_prompt(REPO_ROOT / 'docs' / 'index.md', 'AgentSetup')
    first_trace_prompt = extract_agent_setup_prompt(REPO_ROOT / 'docs' / 'first-trace.md', 'CopyPrompt')

    assert index_prompt == first_trace_prompt


def test_agent_setup_prompt_states_the_load_bearing_content() -> None:
    """Pins content, not just cross-file symmetry -- a future edit that drops the
    auth-first gate or the skill fetch would leave both pages agreeing with each
    other but silently wrong; this fails independently of that comparison.
    """
    prompt = extract_agent_setup_prompt(REPO_ROOT / 'docs' / 'index.md', 'AgentSetup')

    assert (
        'https://raw.githubusercontent.com/pydantic/logfire/refs/heads/main/logfire/.agents/skills/logfire-setup/SKILL.md'
        in prompt
    )
    assert 'Authenticate first, confirmed via `whoami`, before opening or running any application file' in prompt


def test_setup_skills_prioritize_one_service_reaching_first_data() -> None:
    hub = (REPO_ROOT / 'logfire' / '.agents' / 'skills' / 'logfire-setup' / 'SKILL.md').read_text()
    instrumentation = (
        REPO_ROOT / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation' / 'SKILL.md'
    ).read_text()

    assert 'get one representative application service to verified first data' in hub
    assert 'choose one representative service with the shortest path' in instrumentation
    assert 'Do not instrument every detected language or package during the first pass' in instrumentation
    assert 'first get the representative service to verified first data' in instrumentation
    assert 'verifying each source before adding the next' in instrumentation
    assert 'Follow every applicable subsection' not in instrumentation


def _wrap(component: str, prompt_lines: list[str]) -> str:
    return f'<{component}>\n\n````text\n' + '\n'.join(prompt_lines) + f'\n````\n\n</{component}>\n'


def test_extract_agent_setup_prompt_accepts_an_embedded_fence_shorter_than_the_outer_one(tmp_path: Path) -> None:
    path = tmp_path / 'with-embedded-fence.md'
    path.write_text(
        _wrap('AgentSetup', ['Some setup text with an example:', '', '```', 'inner content', '```', '', 'More text.'])
    )

    prompt = extract_agent_setup_prompt(path, 'AgentSetup')

    assert 'inner content' in prompt


def test_extract_agent_setup_prompt_rejects_an_embedded_fence_as_long_as_the_outer_one(tmp_path: Path) -> None:
    # The outer fence is 4 backticks (opened by `_wrap` as ````text); an inner fence of
    # the same length would close the outer block early in real markdown rendering, so
    # this must fail loudly rather than silently accept malformed content.
    path = tmp_path / 'bad-embedded-fence.md'
    path.write_text(
        _wrap('AgentSetup', ['Some setup text with an example:', '', '````', 'inner content', '````', '', 'More text.'])
    )

    with pytest.raises(AssertionError):
        extract_agent_setup_prompt(path, 'AgentSetup')
