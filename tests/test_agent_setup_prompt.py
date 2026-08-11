from pathlib import Path

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

    embedded_fence_lengths = [len(line) - len(line.lstrip('`')) for line in lines[1:-1] if line.startswith('`')]
    assert embedded_fence_lengths
    assert len(fence) > max(embedded_fence_lengths)

    prompt = '\n'.join(lines[1:-1])
    assert prompt
    return prompt


def test_agent_setup_prompts_match() -> None:
    index_prompt = extract_agent_setup_prompt(REPO_ROOT / 'docs' / 'index.md', 'AgentSetup')
    first_trace_prompt = extract_agent_setup_prompt(REPO_ROOT / 'docs' / 'first-trace.md', 'CopyPrompt')

    assert index_prompt == first_trace_prompt
