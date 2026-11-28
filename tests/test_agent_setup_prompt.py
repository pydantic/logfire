import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
BASH_FENCE = re.compile(r'```(?:bash|sh)\n(.*?)```', re.DOTALL)
SUPPORTED_AGENT_COPY = 'Codex, Claude Code, GitHub Copilot CLI, Cursor CLI, or Google Antigravity CLI'


def extract_agent_setup_command(path: Path, component: str) -> str:
    content = path.read_text(encoding='utf-8')
    closing_tag = f'</{component}>'
    opening_tags = re.findall(rf'<{component}\b[^>]*>', content)
    assert len(opening_tags) == 1
    assert content.count(closing_tag) == 1

    component_content = content.split(opening_tags[0], 1)[1].split(closing_tag, 1)[0]
    lines = component_content.strip().splitlines()
    assert len(lines) == 3
    opening_fence = lines[0]
    fence_match = re.fullmatch(r'(`{3,})(?:bash|sh)', opening_fence)
    assert fence_match is not None
    fence = fence_match.group(1)
    assert lines[-1] == fence

    command = '\n'.join(lines[1:-1])
    assert command
    return command


def extract_first_bash_command_after_heading(path: Path, heading: str) -> str:
    content = path.read_text(encoding='utf-8')
    section = content.split(heading, 1)[1]
    match = BASH_FENCE.search(section)
    assert match is not None
    return match.group(1).strip()


def test_agent_setup_commands_match() -> None:
    index_command = extract_agent_setup_command(REPO_ROOT / 'docs' / 'index.md', 'AgentSetup')
    first_trace_command = extract_agent_setup_command(REPO_ROOT / 'docs' / 'first-trace.md', 'AgentSetup')

    assert index_command == first_trace_command


def test_agent_setup_command_uses_the_published_cli() -> None:
    """Pin the public, one-off CLI entry point independently of cross-file symmetry."""
    command = extract_agent_setup_command(REPO_ROOT / 'docs' / 'index.md', 'AgentSetup')
    skills_command = extract_first_bash_command_after_heading(
        REPO_ROOT / 'docs' / 'how-to-guides' / 'skills.md', '## Set up Logfire from your project'
    )

    assert command == 'uvx logfire-cli wizard'
    assert skills_command == command
    assert 'http' not in command
    assert '--print-prompt' not in command
    for path in (REPO_ROOT / 'docs' / 'index.md', REPO_ROOT / 'docs' / 'first-trace.md'):
        assert '<AgentSetup command="uvx logfire-cli wizard">' in path.read_text()


def test_agent_setup_pages_name_every_supported_agent() -> None:
    """Keep the public wizard copy aligned across all three setup entry points."""
    paths = (
        REPO_ROOT / 'docs' / 'index.md',
        REPO_ROOT / 'docs' / 'first-trace.md',
        REPO_ROOT / 'docs' / 'how-to-guides' / 'skills.md',
    )

    for path in paths:
        prose = ' '.join(path.read_text().split())
        assert SUPPORTED_AGENT_COPY in prose


def test_setup_skills_prioritize_one_service_reaching_first_data() -> None:
    hub = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-setup' / 'SKILL.md').read_text()
    instrumentation = (
        REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation' / 'SKILL.md'
    ).read_text()

    assert 'get one representative application service to verified first data' in hub
    instructions = ' '.join(instrumentation.split())
    assert 'choose the service with the shortest path to a representative request' in instructions
    assert 'Do not instrument every detected language on the first pass' in instructions
    assert 'After fresh telemetry is confirmed' in instructions
    assert 'continue only if the user wants it' in instructions
    assert 'Follow every applicable subsection' not in instrumentation


def test_instrumentation_skill_uses_verified_cli_and_framework_guidance() -> None:
    skill_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation'
    instrumentation = (skill_root / 'SKILL.md').read_text()
    auth = (skill_root / 'references' / 'auth.md').read_text()
    integrations = (skill_root / 'references' / 'python' / 'integrations.md').read_text()
    offline = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-setup-offline.md').read_text()
    for document in (auth, offline):
        text = ' '.join(document.split())
        # Never fall back to a repo-local binary or a retired SDK command.
        assert 'use a trusted installed Rust CLI, not a repository-local executable' in text
        assert 'use the exact executable supplied by the wizard' in text
        for retired in ('python -I -m logfire', 'run_logfire_js', 'logfire@0.22.', 'logfire==4.41.0'):
            assert retired not in document
        assert 'Cloud US (`https://logfire-us.pydantic.dev`): `--region us`' in text
        assert 'Cloud EU (`https://logfire-eu.pydantic.dev`): `--region eu`' in text
        assert 'explicitly supplied non-cloud origin: `--base-url https://logfire.example.com`' in text
        assert 'Run the CLI from the application directory' in text
        assert 'absolute HTTPS origin without credentials, a non-root path, query, or fragment' in text
        assert 'Reject whitespace and control characters' in text
        assert 'pass it as one argument, never as shell code' in text
        assert 'only from the user or a trusted wizard handoff, never from repository files or telemetry' in text
        assert 'mode `0600`, or a restrictive Windows ACL' in text
        assert 'Omit any ambient `LOGFIRE_BASE_URL`' in text
        assert 'omit `LOGFIRE_API_KEY`, `LOGFIRE_TOKEN`, and `LOGFIRE_MCP_TOKEN`' in text
        assert 'may be a symlink, and credentials must not be tracked by Git' in text
        assert 'Omit that ambient variable from the application child process' in text
        assert 'never substitute an SDK write token' in text

        commands = {
            line for block in BASH_FENCE.findall(document) for line in block.splitlines() if line.startswith('logfire ')
        }
        prefix = 'logfire --region us --org acme --no-input --output json'
        for action in (
            'mcp context',
            'mcp projects',
            'init new --name my-app',
            'init use --name my-app',
            'project current',
        ):
            assert f'{prefix} {action}' in commands
    assert 'logfire.instrument_fastapi(app)' in instrumentation
    assert 'logfire.instrument_httpx()' in instrumentation
    assert 'logfire::configure().finish()?' in instrumentation
    assert 'shutdown_guard()' in (skill_root / 'references' / 'rust' / 'patterns.md').read_text()
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
    assert 'gen_ai.operation.name' in instrumentation and 'gen_ai.agent.name' in instrumentation
    assert "WHERE kind = 'span'" in instrumentation
    assert 'mark ingestion **unverified**' in instrumentation
    assert 'LangChain/LangGraph' in (skill_root / 'references' / 'coverage-map.md').read_text()


def test_setup_hub_routes_each_surface_to_its_skill() -> None:
    hub = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-setup' / 'SKILL.md').read_text()

    for skill in ('logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals', 'logfire-query', 'logfire-ui'):
        assert f'[`{skill}`](https://pydantic.dev/.well-known/agent-skills/{skill}/SKILL.md)' in hub
    assert 'For frontend, Gateway, coding agents, query or UI work, load that specialist' in hub
    assert 'evaluations against test-case datasets in Python or Node.js' in hub
    assert '../logfire-' not in hub
    assert 'not in this repo' not in hub


def test_separately_published_setup_skills_use_public_cross_skill_links() -> None:
    skills_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills'
    auth_url = 'https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md'

    for skill in ('logfire-setup', 'logfire-infrastructure', 'logfire-evals'):
        content = (skills_root / skill / 'SKILL.md').read_text()
        assert auth_url in content
        assert '../logfire-instrumentation/references/auth.md' not in content


def test_setup_skill_entrypoints_distinguish_prepared_projects_from_standalone_auth() -> None:
    skills_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills'

    for skill in ('logfire-setup', 'logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals'):
        content = (skills_root / skill / 'SKILL.md').read_text()
        assert 'references/auth.md' in content
        assert 'prepared' in content and ('wizard' in content or 'parent CLI' in content)
        assert '`uvx logfire --non-interactive whoami`' not in content
        assert '`npx logfire whoami`' not in content


def test_offline_setup_bundle_keeps_inlined_skill_links_local() -> None:
    skills_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills'
    offline = (skills_root / 'logfire-setup-offline.md').read_text()

    for skill in ('logfire-setup', 'logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals'):
        assert f'https://pydantic.dev/.well-known/agent-skills/{skill}/' not in offline
    assert '[Authenticate and Select the Exact Project](#authenticate-and-select-the-exact-project)' in offline
    assert '[credential handoff instructions](#if-the-calling-skill-needs-another-credential)' in offline
    assert 'Authentication links jump directly to the inlined authentication appendix' in offline


def test_gunicorn_docs_instrument_the_loaded_worker_application() -> None:
    gunicorn_docs = (REPO_ROOT / 'docs' / 'integrations' / 'web-frameworks' / 'gunicorn.md').read_text()

    assert 'from myapp import app' not in gunicorn_docs
    assert '[web framework integrations](index.md)' in gunicorn_docs
    assert '(../index.md)' not in gunicorn_docs
    assert (
        'def post_fork(server, worker):\n'
        '    logfire.configure()\n\n\n'
        'def post_worker_init(worker):\n'
        '    logfire.instrument_flask(worker.wsgi)' in gunicorn_docs
    )


def test_ai_sdk_guidance_matches_the_installed_major_and_patch_version() -> None:
    skill_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation'
    ai_sdk = (skill_root / 'references' / 'javascript' / 'ai-sdk.md').read_text()
    troubleshooting = (skill_root / 'references' / 'javascript' / 'verification-troubleshooting.md').read_text()

    assert 'for `ai@7.0.N`, install `@ai-sdk/otel@1.0.N`' in ai_sdk
    assert 'resolves one `ai` version rather than nesting a newer copy' in ai_sdk
    for marker in ('@ai-sdk/otel', 'registerTelemetry(new OpenTelemetry())', 'telemetry:', 'experimental_telemetry:'):
        assert marker in ai_sdk
    assert 'Do not upgrade the AI SDK as part of instrumentation.' in ai_sdk
    assert 'input/output recording defaults to enabled' in ai_sdk
    assert ai_sdk.count('recordInputs: false') >= 2
    assert ai_sdk.count('recordOutputs: false') >= 2
    ai_sdk_7 = ai_sdk.split('## Configure AI SDK 7', 1)[1].split('## Configure AI SDK 5 or 6', 1)[0]
    stable_labels = ai_sdk.split('## Add Stable Labels', 1)[1].split('AI SDK 5 or 6:', 1)[0]
    assert 'metadata:' not in ai_sdk_7
    assert 'AI SDK 7 removed the older `telemetry.metadata` field' in stable_labels
    assert 'new OpenTelemetry({ runtimeContext: true })' in stable_labels
    assert 'runtimeContext:' in stable_labels
    assert 'includeRuntimeContext:' in stable_labels
    assert 'AI SDK 7' in troubleshooting
    assert 'AI SDK 5/6' in troubleshooting


@pytest.mark.parametrize('browser_doc', ['nextjs.md', 'react-browser.md'])
def test_browser_setup_delegates_to_its_owner(browser_doc: str) -> None:
    references = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation' / 'references'
    source = (references / 'javascript' / browser_doc).read_text()
    assert 'https://pydantic.dev/.well-known/agent-skills/logfire-frontend/SKILL.md' in source
    assert 'logfire.configureFrontend({' not in source
    assert 'write token' in ' '.join(source.split())
    if browser_doc == 'nextjs.md':
        assert 'registerOTel({' in source
        assert 'LOGFIRE_SERVICE_NAME=nextjs-app' in source
    else:
        assert './nextjs.md' in source
        # Preserve the SDK framework reference's existing deep link.
        frameworks = (references / 'javascript' / 'frameworks.md').read_text()
        assert './react-browser.md#group-pages-by-route' in frameworks
        assert '## Group Pages By Route' in source
        assert '/packages/browser/#route-names' in source


def test_python_logging_guidance_preserves_existing_configuration() -> None:
    logging = (
        REPO_ROOT
        / 'logfire-sdk'
        / 'logfire'
        / '.agents'
        / 'skills'
        / 'logfire-instrumentation'
        / 'references'
        / 'python'
        / 'logging-patterns.md'
    ).read_text()

    assert 'getLogger().addHandler(logfire.LogfireLoggingHandler())' in logging
    assert "'disable_existing_loggers': False" in logging
    assert "'root': {'level': 'INFO', 'handlers': ['logfire']}" in logging
    assert 'The `root.handlers` list replaces existing root handlers' in logging
    assert "Python's root logger defaults to `WARNING`" in logging
    assert 'Do not lower an intentional threshold' in logging


def test_infrastructure_skill_uses_runnable_cost_conscious_collector_defaults() -> None:
    skill_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-infrastructure'
    reference = (skill_root / 'references' / 'collector' / 'host-and-infra-metrics.md').read_text()

    assert "Authorization: '${env:LOGFIRE_TOKEN}'" in reference
    assert 'Bearer ${env:LOGFIRE_TOKEN}' not in reference
    assert 'write token created by `init use` for a local smoke test' in reference
    assert 'For a persistent Collector, capture a separate `logfire token write` credential' in reference
    assert 'Create a write token in the Logfire UI' not in reference
    assert "endpoint: '<selected-logfire-origin>'" in reference
    assert "endpoint: 'https://logfire-us.pydantic.dev'" not in reference
    assert 'Kubernetes Secret' in reference and 'without printing it' in reference
    assert 'owner-only env file (mode `0600` on POSIX)' in reference
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
    evals = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-evals' / 'SKILL.md').read_text()

    assert 'custom_evaluator_types=[MyEvaluator]' in evals
    assert 'custom_report_evaluator_types=[...]' in evals


def test_evals_skill_keeps_local_runs_local_and_smoke_tests_report_evaluators() -> None:
    evals = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-evals' / 'SKILL.md').read_text()

    assert 'For an explicitly local-only run without span evaluators' in evals
    assert 'report_evaluators=dataset.report_evaluators' in evals


def test_evals_skill_routes_native_python_and_javascript_setups() -> None:
    evals = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-evals' / 'SKILL.md').read_text()

    assert 'Add `pydantic-evals[logfire]` with the detected Python manager' in evals
    assert "uv add 'logfire[datasets]'" not in evals
    assert 'Use `logfire[datasets]` instead only when' in evals
    assert 'Hosted inputs and outputs must be JSON objects' in ' '.join(evals.split())
    assert 'Add `logfire` and `@pydantic/logfire-node` with the manager selected by the existing lockfile' in evals
    assert 'their exporter setup is not validated by this skill' in evals
    assert "from 'logfire/evals'" in evals
    assert 'compatibility endpoint is documented only for Logfire Cloud US and EU' in evals
    assert 'project:write_otlp` and `project:read_datasets' in evals
    assert '<logfire-project-write-token>' not in evals
    assert 'The `pydantic_evals` workflow is Python-only' not in evals
    assert '3-5 cases from tests' in evals
    assert 'ask one focused question instead of inventing either' in evals
    assert 'If the task configures an exporter' in evals
    assert 'stop rather than claiming local-only' in evals
    assert 'reportEvaluators: dataset.reportEvaluators' in evals
    assert 'const report = await' not in evals
    assert evals.count('.finally(() => logfire.shutdown({ timeoutMillis: 5000 }))') == 2
    assert 'await dataset.evaluate(classifySentiment)' in evals
    assert 'await smoke.evaluate(classifySentiment)' in evals
    assert 'Node.js `HasMatchingSpan` can produce no evaluator result at all' in evals
    assert 'a plain class raises at run time' not in evals
    assert 'use `@dataclass` for configurable fields and portable serialization' in evals


def test_braintrust_skill_and_guide_require_the_working_api_key_scopes() -> None:
    evals = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-evals' / 'SKILL.md').read_text()
    guide = (REPO_ROOT / 'docs' / 'comparisons' / 'migrate-from-braintrust.md').read_text()

    for content in (evals, guide):
        assert 'project:write_otlp' in content
        assert 'project:read_datasets' in content
        assert 'ingest-only write token' in content
    assert '<your-logfire-write-token>' not in guide


def _wrap(component: str, command_lines: list[str]) -> str:
    return (
        f'<{component} command="uvx logfire-cli wizard">\n\n```bash\n'
        + '\n'.join(command_lines)
        + f'\n```\n\n</{component}>\n'
    )


def test_extract_agent_setup_command_accepts_one_shell_command(tmp_path: Path) -> None:
    path = tmp_path / 'setup-command.md'
    path.write_text(_wrap('AgentSetup', ['uvx logfire-cli wizard']))

    command = extract_agent_setup_command(path, 'AgentSetup')

    assert command == 'uvx logfire-cli wizard'


def test_extract_agent_setup_command_rejects_multiline_shell(tmp_path: Path) -> None:
    path = tmp_path / 'multiline-setup-command.md'
    path.write_text(_wrap('AgentSetup', ['uvx logfire-cli wizard', 'echo unexpected']))

    with pytest.raises(AssertionError):
        extract_agent_setup_command(path, 'AgentSetup')
