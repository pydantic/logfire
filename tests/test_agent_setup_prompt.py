import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
BASH_FENCE = re.compile(r'```(?:bash|sh)\n(.*?)```', re.DOTALL)


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


def test_setup_skills_prioritize_one_service_reaching_first_data() -> None:
    hub = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-setup' / 'SKILL.md').read_text()
    instrumentation = (
        REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation' / 'SKILL.md'
    ).read_text()

    assert 'get one representative application service to verified first data' in hub
    assert 'choose one representative service with the shortest path' in instrumentation
    assert 'Do not instrument every detected language or package during the first pass' in instrumentation
    assert 'first get the representative service to verified first data' in instrumentation
    assert 'verifying each source before adding the next' in instrumentation
    assert 'Follow every applicable subsection' not in instrumentation


def test_instrumentation_skill_uses_verified_cli_and_framework_guidance() -> None:
    skill_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation'
    instrumentation = (skill_root / 'SKILL.md').read_text()
    auth = (skill_root / 'references' / 'auth.md').read_text()
    integrations = (skill_root / 'references' / 'python' / 'integrations.md').read_text()
    offline = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-setup-offline.md').read_text()
    npm_exec = (
        'env -u LOGFIRE_TOKEN -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ '
        '--cache "$npm_cache" --ignore-scripts --script-shell=/bin/sh --node-options=\'\' '
        '--prefix "$npm_prefix" exec --yes --package=logfire@0.22.8 -- logfire'
    )

    assert 'https://logfire-us.pydantic.dev` -> `--region us' in auth
    assert 'https://logfire-eu.pydantic.dev` -> `--region eu' in auth
    assert 'Logfire Cloud is the normal customer path and uses a region' in auth
    assert 'An explicitly supplied non-cloud Logfire origin -> `--base-url <exact-origin>`' in auth
    assert 'this means an on-prem Logfire deployment' in auth
    assert 'never replace a Logfire Cloud region with `--base-url`' in auth
    assert 'Require `https://` for a non-cloud origin' in auth
    assert 'loopback' not in auth
    assert 'development origin' not in auth
    assert 'accept only an absolute origin' in auth
    assert 'no userinfo, non-root path, query, fragment, whitespace, or control characters' in auth
    assert 'check only whether `LOGFIRE_TOKEN` is set; never read its value' in auth
    assert 'Every CLI command below excludes that ambient token' in auth
    assert 'do not make an exception' in auth
    assert 'never concatenate it into shell text or use `eval`' in auth
    assert 'omit `<target>` from the initial check' not in auth
    assert '<target> projects new <project-name>' in auth
    assert 'product prompt only needs to supply the exact Logfire URL' in auth
    assert '--region eu auth' not in auth
    assert 'python -I -m logfire' in auth
    assert 'run_logfire_js() {' in auth
    assert npm_exec in auth
    assert 'logfire@0.22.8' in auth
    assert 'logfire@0.22.5' not in auth
    assert '$(mktemp -d)" exec' not in auth
    assert 'run_logfire_js <target> projects list --json' not in auth
    assert 'run_logfire_js <target> projects list\n' in auth
    assert auth.count('whoami --data-dir "$credential_probe_dir"') == 2
    assert auth.count('credential_probe_dir="$(mktemp -d)" || exit 1') == 2
    assert auth.count('trap \'rm -rf -- "$credential_probe_dir"\' EXIT') == 2
    assert 'these commands use the user credential bound to the selected origin' in auth
    assert 'Do not pass the temporary data directory to `projects use` or the final check' in auth
    assert 'The command blocks above are POSIX shell' in auth
    assert 'child process whose environment omits `LOGFIRE_TOKEN`' in auth
    assert 'a later application process can still inherit that variable' in auth
    for document in (auth, offline):
        assert 'ask whether the account is in the US or EU before running the CLI' in document
        assert 'Never run targetless `whoami` or `auth`' in document
        assert 'Use the explicit region throughout' in document
        assert 'use only that exact target' in document
        assert 'ask instead of substituting another' in document
        assert 'when several exist' in document
        assert 'only in that last, zero-project case' in document
    assert 'omit that variable from the child application process too' in instrumentation
    for document in (auth, instrumentation, offline):
        assert not any(line.lstrip().startswith('npx') and 'logfire' in line for line in document.splitlines())
        assert 'logfire@0.22.5' not in document
        for fence in BASH_FENCE.findall(document):
            if re.search(r'^\s*run_logfire_js\s', fence, re.MULTILINE):
                assert 'run_logfire_js() {' in fence
                assert npm_exec in fence
        for line in document.splitlines():
            if 'uvx --isolated' in line and not line.lstrip().startswith('#'):
                assert line.lstrip().startswith('env -u LOGFIRE_TOKEN ')
    for document in (auth, offline):
        npm_commands = [line.strip() for line in document.splitlines() if 'npm ' in line and '-- logfire' in line]
        assert npm_commands
        assert all(npm_exec in line for line in npm_commands)
    assert 'JS CLI (POSIX shell)' in auth
    assert 'git ls-files -- .logfire' in auth
    assert 'neither\n`.logfire` nor `.logfire/logfire_credentials.json` may be a symlink' in auth
    assert 'use the external-prefix npm fallback' in instrumentation
    assert 'a detected FastAPI service that also uses HTTPX' in instrumentation
    assert "uv run --with 'logfire==4.41.0' logfire --non-interactive run --summary" in instrumentation
    assert 'run_logfire_js <target> projects status --json' in instrumentation
    assert 'The commands below always exclude an ambient `LOGFIRE_TOKEN`' in instrumentation
    assert 'omit that exclusion' not in instrumentation
    assert (
        "uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive "
        '<target> read-tokens --project <organization>/<project> create --save' in instrumentation
    )
    assert 'run_logfire_js <target> read-tokens --project <organization>/<project> create --save' in instrumentation
    assert 'cargo add logfire' in instrumentation
    assert 'logfire = "0.6"' not in instrumentation
    assert 'shutdown_guard()' in instrumentation
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
    hub = (REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-setup' / 'SKILL.md').read_text()

    for skill in ('logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals', 'logfire-query', 'logfire-ui'):
        assert f'[`{skill}`](https://pydantic.dev/.well-known/agent-skills/{skill}/SKILL.md)' in hub
    assert '"set up evals for this agent"' in hub
    assert 'evaluations against test-case datasets in Python or Node.js' in hub
    assert '../logfire-' not in hub
    assert 'not in this repo' not in hub
    assert 'ask whether the account is in the US or EU' in hub
    assert 'never infer it from a saved session' in hub


def test_separately_published_setup_skills_use_public_cross_skill_links() -> None:
    skills_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills'
    auth_url = 'https://pydantic.dev/.well-known/agent-skills/logfire-instrumentation/references/auth.md'

    for skill in ('logfire-setup', 'logfire-infrastructure', 'logfire-evals'):
        content = (skills_root / skill / 'SKILL.md').read_text()
        assert auth_url in content
        assert '../logfire-instrumentation/references/auth.md' not in content


def test_setup_skill_entrypoints_delegate_target_aware_whoami_to_auth_reference() -> None:
    skills_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills'

    for skill in ('logfire-setup', 'logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals'):
        content = (skills_root / skill / 'SKILL.md').read_text()
        assert 'target-aware `whoami` check' in content
        assert 'right project and resolved `--region` or `--base-url` target' in content
        assert '`uvx logfire --non-interactive whoami`' not in content
        assert '`npx logfire whoami`' not in content


def test_offline_setup_bundle_keeps_inlined_skill_links_local() -> None:
    skills_root = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills'
    offline = (skills_root / 'logfire-setup-offline.md').read_text()

    for skill in ('logfire-setup', 'logfire-instrumentation', 'logfire-infrastructure', 'logfire-evals'):
        assert f'https://pydantic.dev/.well-known/agent-skills/{skill}/' not in offline
    assert '[Authenticate and Select the Exact Project](#authenticate-and-select-the-exact-project)' in offline
    assert '[auth.md](#if-the-calling-skill-needs-a-write-token-not-just-a-cli-session)' in offline
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


def test_browser_guidance_uses_restricted_frontend_application_direct_ingest() -> None:
    references = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation' / 'references'
    skill = (references.parent / 'SKILL.md').read_text()
    nextjs = (references / 'javascript' / 'nextjs.md').read_text()
    react = (references / 'javascript' / 'react-browser.md').read_text()
    installation = (references / 'javascript' / 'installation-and-env.md').read_text()
    frameworks = (references / 'javascript' / 'frameworks.md').read_text()
    troubleshooting = (references / 'javascript' / 'verification-troubleshooting.md').read_text()

    for source in (skill, nextjs, react, installation, frameworks, troubleshooting):
        assert 'Browser telemetry must go through an authenticated backend proxy' not in source
        assert 'Browser traces must go through an authenticated same-origin backend proxy' not in source
        assert 'Browser code must use a proxy URL' not in source

    for source in (nextjs, react):
        guidance = ' '.join(source.split())
        assert 'logfire.configureFrontend({' in source
        assert "baseUrl: '<generated-regional-base-url>'" in source
        assert "token: '<frontend-application-token>'" in source
        assert 'Replace both placeholders before deploying' in source
        assert 'Frontend → Applications' in source
        assert '0.21.0 or later' in source
        assert 'auto-instrumentation and Web Vitals metrics by default' in source
        assert '`autoInstrumentations: false` to disable automatic instrumentation' in source
        assert '`rum: { webVitals: false }` to disable Web Vitals spans and metrics' in source
        assert '`rum: { webVitals: { metrics: false } }` to keep Web Vitals spans without metrics' in source
        assert 'LOGFIRE_PROXY_ALLOWED_ORIGIN' in source
        assert 'Reject requests when that configuration is absent' in guidance
        assert 'the `Origin` header is missing, or it does not match' in source
        assert 'Do not derive the allowed origin from the incoming request' in guidance
        assert (
            'https://pydantic.dev/docs/logfire/instrument/typescript/packages/browser/#optional-backend-proxy' in source
        )
        assert 'traceExporterHeaders:' not in source
        assert '@opentelemetry/auto-instrumentations-web' not in source

    assert 'optional-proxy contract' in nextjs
    assert 'Optional Backend Proxy' in react
    assert 'restricted public token and regional base URL generated for a frontend application' in skill
    assert 'restricted public token' in installation
    assert 'Never reuse `LOGFIRE_TOKEN` or another ordinary write token in the browser' in installation
    assert '`/v1/traces` URL derived from the regional `baseUrl`' in troubleshooting


def test_browser_framework_examples_configure_once_without_strict_mode_shutdown() -> None:
    references = REPO_ROOT / 'logfire-sdk' / 'logfire' / '.agents' / 'skills' / 'logfire-instrumentation' / 'references'
    for browser_doc in ('javascript/nextjs.md', 'javascript/react-browser.md'):
        browser = (references / browser_doc).read_text()
        assert 'useRef(false)' in browser
        assert 'if (!configured.current)' in browser
        effect_body = browser.split('useEffect(() => {', 1)[1].split('\n  }, [])', 1)[0]
        assert '\n    return ' not in effect_body
        assert '\n      return ' not in effect_body
    assert 'Import this Client Component normally' in (references / 'javascript/nextjs.md').read_text()


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
    assert "write token created by the authentication flow's `projects use`" in reference
    assert 'Create a write token in the Logfire UI' not in reference
    assert "endpoint: '<selected-logfire-origin>'" in reference
    assert "endpoint: 'https://logfire-us.pydantic.dev'" not in reference
    assert (
        '--dry-run=client -o yaml | kubectl apply -f -'
        in (skill_root.parent / 'logfire-instrumentation' / 'references' / 'auth.md').read_text()
    )
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
    assert 'Hosted inputs and outputs must be JSON objects' in evals
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
