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

    assert 'https://pydantic.dev/.well-known/agent-skills/logfire-setup/SKILL.md' in prompt
    assert 'raw.githubusercontent.com' not in prompt
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


def test_instrumentation_skill_uses_verified_cli_and_framework_guidance() -> None:
    skill_root = REPO_ROOT / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation'
    instrumentation = (skill_root / 'SKILL.md').read_text()
    auth = (skill_root / 'references' / 'auth.md').read_text()
    integrations = (skill_root / 'references' / 'python' / 'integrations.md').read_text()

    assert '--region <region> auth' in auth
    assert '--region eu auth' not in auth
    assert 'python -I -m logfire' in auth
    assert (
        'env -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ exec --yes --ignore-scripts '
        '--prefix "$(mktemp -d)" --package=logfire@0.22.5' in auth
    )
    assert '\nnpx logfire' not in auth
    assert 'JS CLI (POSIX shell)' in auth
    assert 'git ls-files -- .logfire' in auth
    assert 'neither\n`.logfire` nor `.logfire/logfire_credentials.json` may be a symlink' in auth
    assert 'a detected FastAPI service that also uses HTTPX' in instrumentation
    assert "uv run --with 'logfire==4.41.0' logfire --non-interactive run --summary" in instrumentation
    assert 'cargo add logfire' in instrumentation
    assert 'logfire = "0.6"' not in instrumentation
    assert '`app = logfire.instrument_asgi(app)`' in integrations
    assert '`app = logfire.instrument_wsgi(app)`' in integrations
    assert '`logfire.instrument_django()` | No' in integrations
    assert '`openai-agents` installed; imports as `agents`' in integrations
    assert 'from myapp import app' not in integrations
    assert (
        'def post_fork(server, worker):\n'
        '    logfire.configure()\n\n\n'
        'def post_worker_init(worker):\n'
        '    logfire.instrument_flask(worker.wsgi)' in integrations
    )
    assert 'Agent runs + tokens + tool calls + messages (no cost yet)' in instrumentation
    assert 'LangGraph agents produce an agent root' in instrumentation
    assert 'Neither path marks an agent root span' not in instrumentation
    assert 'what Steps 3-4 covered' in instrumentation


def test_setup_hub_routes_each_surface_to_its_skill() -> None:
    hub = (REPO_ROOT / 'logfire' / '.agents' / 'skills' / 'logfire-setup' / 'SKILL.md').read_text()

    for skill in ('logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals'):
        assert f'[`{skill}`](../{skill}/SKILL.md)' in hub
    for skill in ('logfire-query', 'logfire-ui'):
        assert f'[`{skill}`](https://pydantic.dev/.well-known/agent-skills/{skill}/SKILL.md)' in hub
    assert 'not in this repo' not in hub


def test_gunicorn_docs_instrument_the_loaded_worker_application() -> None:
    gunicorn_docs = (REPO_ROOT / 'docs' / 'integrations' / 'web-frameworks' / 'gunicorn.md').read_text()

    assert 'from myapp import app' not in gunicorn_docs
    assert (
        'def post_fork(server, worker):\n'
        '    logfire.configure()\n\n\n'
        'def post_worker_init(worker):\n'
        '    logfire.instrument_flask(worker.wsgi)' in gunicorn_docs
    )


def test_infrastructure_skill_uses_runnable_cost_conscious_collector_defaults() -> None:
    skill_root = REPO_ROOT / 'logfire' / '.agents' / 'skills' / 'logfire-infrastructure'
    reference = (skill_root / 'references' / 'collector' / 'host-and-infra-metrics.md').read_text()

    assert "Authorization: 'Bearer ${env:LOGFIRE_TOKEN}'" in reference
    assert 'collection_interval: 60s' in reference
    assert 'system.cpu.utilization:' in reference
    assert 'system.memory.utilization:' in reference
    assert 'system.filesystem.utilization:' in reference
    assert '\n      processes:\n' in reference
    assert '\n      process:\n' not in reference
    assert 'detectors: [env, system]' in reference
    assert '`metrics.queries[].stats` or `metrics.discovery.stats` explicitly' in reference
    assert 'produce Summary points' in reference
    assert 'Logfire drops those points at ingest' in reference


def test_evals_skill_explains_how_to_restore_custom_evaluators() -> None:
    evals = (REPO_ROOT / 'logfire' / '.agents' / 'skills' / 'logfire-evals' / 'SKILL.md').read_text()

    assert 'custom_evaluator_types=[ExactMatch]' in evals
    assert 'custom_report_evaluator_types=[...]' in evals


def test_evals_skill_keeps_local_runs_local_and_smoke_tests_report_evaluators() -> None:
    evals = (REPO_ROOT / 'logfire' / '.agents' / 'skills' / 'logfire-evals' / 'SKILL.md').read_text()

    assert 'Skip authentication and continue to Step 3 only when the user explicitly wants a local-only' in evals
    assert 'report_evaluators=dataset.report_evaluators' in evals


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
