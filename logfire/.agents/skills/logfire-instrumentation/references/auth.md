# Authenticate and Select the Exact Project

Shared by all three Logfire setup skills (instrumentation, infrastructure, evals) — whichever skill you're following, run this once per session; a later skill's own `whoami` check will report "already resolved" and can be skipped.

Choose the CLI target before assuming anything needs to happen. Logfire Cloud is the normal customer path and uses a region. Derive the target from the exact supplied origin and use the same target on every CLI command in this session:

- `https://logfire-us.pydantic.dev` -> `--region us`
- `https://logfire-eu.pydantic.dev` -> `--region eu`
- An explicitly supplied non-cloud Logfire origin -> `--base-url <exact-origin>`. Customer-facing, this means an on-prem Logfire deployment.

Never pass both, and never replace a Logfire Cloud region with `--base-url`. Parse a supplied URL with a standard URL parser and accept only an absolute origin: scheme, valid hostname or IP literal, and optional port, with no userinfo, non-root path, query, fragment, whitespace, or control characters. Normalize only a trailing `/`. Require `https://` for a non-cloud origin because CLI authentication sends a user credential to it. If parsing or validation fails, or the origin uses HTTP, stop and ask for a valid HTTPS origin instead; do not authenticate. Before contacting a non-cloud origin, check only whether `LOGFIRE_TOKEN` is set; never read its value. Every CLI command below excludes that ambient token so it cannot override the selected target; do not make an exception or edit the user's stored environment. After `projects use`, the CLI can use the project credential it created on disk while the ambient token remains excluded. Pass a non-cloud origin as one quoted `--base-url` argument; never concatenate it into shell text or use `eval`. Do not otherwise rewrite, shorten, or guess it. In the commands below, replace `<target>` with the validated selector (`--region us`, `--region eu`, or `--base-url '<canonical-origin>'`). If the request contains no URL and there is no trustworthy region context, omit `<target>` from the initial check; a non-interactive `auth` attempt will print the available region-specific command(s) rather than silently choosing one.

Before trusting repository-local credentials, inspect path metadata only: neither
`.logfire` nor `.logfire/logfire_credentials.json` may be a symlink. In a Git
worktree, `git ls-files -- .logfire` must report nothing except an optional
`.logfire/.gitignore`; a tracked credentials file or tracked `.logfire` directory
is unsafe. Stop and report the unsafe path rather than reading or overwriting it.
This metadata check is allowed before the calling skill's repository-inspection
step; do not open any application or configuration file yet.

Then check, before assuming anything needs to happen. A Logfire Cloud region may use the repository credential because its target is a fixed Logfire origin. An explicitly supplied non-cloud origin is not yet trusted to receive that credential, so point only its initial `whoami` at a fresh empty data directory. A missing project from that isolated probe is expected. Continue with `auth`, `projects list`, and `projects use`: these commands use the user credential bound to the selected origin rather than the repository project credential, and `projects use` replaces that project credential before the normal final `whoami` reads it. Do not pass the temporary data directory to `projects use` or the final check.

With `uv`, use an isolated, config-free, version-pinned environment and invoke Python in isolated mode so repository-local packages and `PYTHONPATH` cannot shadow the CLI:

```bash
# Logfire Cloud:
env -u LOGFIRE_TOKEN uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive <target> whoami

# Explicitly supplied non-cloud origin:
(
  credential_probe_dir="$(mktemp -d)" || exit 1
  trap 'rm -rf -- "$credential_probe_dir"' EXIT
  env -u LOGFIRE_TOKEN uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive --base-url '<canonical-origin>' whoami --data-dir "$credential_probe_dir"
)
```

In a JS/TS project without `uv`, use this POSIX-shell fallback. Include the helper at the start of every JS CLI command block so a fresh shell can run it. The exact package version and `--ignore-scripts` keep the reviewed CLI artifact stable and prevent lifecycle scripts from running:

```bash
npm_cache="$(mktemp -d)"
npm_prefix="$(mktemp -d)"
run_logfire_js() {
  env -u LOGFIRE_TOKEN -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ --cache "$npm_cache" --ignore-scripts --script-shell=/bin/sh --node-options='' --prefix "$npm_prefix" exec --yes --package=logfire@0.22.8 -- logfire "$@"
}

# Logfire Cloud:
run_logfire_js <target> whoami

# Explicitly supplied non-cloud origin:
(
  credential_probe_dir="$(mktemp -d)" || exit 1
  trap 'rm -rf -- "$credential_probe_dir"' EXIT
  run_logfire_js --base-url '<canonical-origin>' whoami --data-dir "$credential_probe_dir"
)
```

Do not use a plain `npx logfire` command or omit the external `--prefix`, shared `--cache`, or Node and shell overrides. The npm CLI does not support `--non-interactive`; without a TTY it fails instead of prompting. The command blocks above are POSIX shell. On Windows, install `uv` from its [official installation guide](https://docs.astral.sh/uv/getting-started/installation/) and launch the same isolated Python arguments through a child process whose environment omits `LOGFIRE_TOKEN`; use the agent runtime's process API rather than translating `env -u`, the subshell, or `trap` into shell text. For the non-cloud probe, pass a newly created temporary directory as `--data-dir` and remove it afterward.

If that already reports the right project and resolved target (`--region` for Logfire Cloud or `--base-url` for an explicitly supplied on-prem origin), you're done — skip straight to the rest of whichever skill sent you here, even if you haven't run `auth` yourself yet. Signing in doesn't have to be your action: the user may have done it in a browser tab left over from an earlier session, or in parallel while you were working on something else. Treat it as good news, not something to question — never undo or re-authenticate over a session that's already valid. Otherwise, run the CLI yourself from the application directory with one of the verified prefixes above — it's a setup tool, not an app dependency. `--non-interactive` is Python-CLI-only right now: the JS CLI doesn't recognize it and errors with "Unknown option" if you pass it — omit it entirely on every JS invocation below; keep it on every Python one. JS `projects list` prints a table to stderr and does not accept `--json`; only `projects status` does.

```bash
# Python CLI (uvx --isolated) -- always include --non-interactive:
env -u LOGFIRE_TOKEN uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive <target> auth
env -u LOGFIRE_TOKEN uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive <target> projects list --json
env -u LOGFIRE_TOKEN uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive <target> projects use <project-name> --org <organization-name>
env -u LOGFIRE_TOKEN uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive <target> whoami

# JS CLI (POSIX shell) -- include the helper in this shell; drop --non-interactive:
npm_cache="$(mktemp -d)"
npm_prefix="$(mktemp -d)"
run_logfire_js() {
  env -u LOGFIRE_TOKEN -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ --cache "$npm_cache" --ignore-scripts --script-shell=/bin/sh --node-options='' --prefix "$npm_prefix" exec --yes --package=logfire@0.22.8 -- logfire "$@"
}
run_logfire_js <target> auth
run_logfire_js <target> projects list
run_logfire_js <target> projects use <project-name> --org <organization-name>
run_logfire_js <target> whoami
```

**On the Python CLI, always put `--non-interactive` immediately after `logfire`.** Without it, a question with nobody to answer it can block on a read that never returns.

- `<target>` is a global option: put it after `--non-interactive` on Python commands and immediately after `logfire` on JavaScript commands, before the subcommand. The product prompt only needs to supply the exact Logfire URL; this reference owns the `--region` versus `--base-url` distinction.
- `auth` with `--non-interactive` does **not** open a browser — it prints a URL and polls for you to finish. Relay that URL to the user; don't wait silently. When the command succeeds, continue immediately with `projects list`; once the project is identified, run `projects use` and `whoami` in the same setup run. Do not end the task merely after browser approval. If project selection is ambiguous, ask the user rather than guessing. Authentication alone does not connect the repository to the project, while `projects use` creates the project credential the application needs.
- `projects list`: Python takes `--json` on this subcommand; the JS CLI prints a table to stderr and ignores `--json` here. Exactly one project returned? Use it. Several plausible and none identified? Ask the user. None exist? Use `<target> projects new <project-name> --org <organization-name>` with the same verified CLI prefix instead.

- Any command failing with `NonInteractiveError` explains what to do next in its own message — usually the exact missing flag (commonly `--org`), but `auth` with no region instead prints a runnable `--region <id> auth` line per region. Follow what the message says and retry once. Don't drop `--non-interactive` to make the error go away; that trades a clear message for the hang it exists to prevent.
- `whoami`'s org/project/region is what every later step must match — instrumentation, verification, any link you give the user. Never substitute a different or "latest" project.
- The CLI commands above exclude ambient `LOGFIRE_TOKEN`, but a later application process can still inherit that variable and silently override the `.logfire/` project credential. During local verification, launch the application through a child environment that also omits the ambient token and make sure its env loader does not reintroduce an unrelated token. Do not mutate the parent shell or silently rewrite the application's existing environment files.
- Never print, log, hard-code, commit, or echo a token, and don't read `~/.logfire/default.toml`'s contents — a bad or missing credential surfaces as a CLI error, not a prompt. The one exception is reading `.logfire/logfire_credentials.json`'s `token` key programmatically, and only to hand it to a non-native-SDK application language that needs the actual value (see below) — never to print, display, or otherwise surface it.

## If the calling skill needs a write token, not just a CLI session

Some callers need an actual token value, not just an authenticated CLI session. `projects use` creates a project-scoped write token and stores it in the gitignored `.logfire/logfire_credentials.json`; do not mint a second token merely because a non-SDK process needs the value:

- **A setup with no Logfire SDK reading local credentials for it** needs a write token for its OTLP exporter's Authorization header. Check the language's own instrumentation reference for whether its SDK already handles this. When nothing does, reuse the credential `projects use` created: read only the `token` key programmatically and write it directly into the runtime's existing gitignored local secret mechanism, without sending the value to stdout, stderr, shell history, source control, or chat.
- An **OpenTelemetry Collector** can use that same CLI-created write token. For Docker or a local host, write a mode-`0600`, gitignored env file such as `.logfire/logfire.env` and configure the Collector to load it. For Kubernetes, create or update the Secret from that env file with `kubectl create secret generic logfire-token --from-env-file=.logfire/logfire.env --dry-run=client -o yaml | kubectl apply -f -`; the dry run emits the manifest directly to `apply` without persisting or displaying an intermediate secret. Use the deployment's secret manager instead when one already exists.
- If `projects use` cannot create the credential because the authenticated user lacks `write_token` permission, stop and ask a project administrator to provide or install an appropriate credential through their normal secret-management path. Never ask anyone to paste a token into the agent chat.
- An **API key** for `LogfireAPIClient` (hosted-dataset push/pull) comes from **Settings → API Keys**, scoped `project:read_datasets`/`project:write_datasets` — a generic write/read token lacks those scopes.

Same rule applies to all three: never print, log, hard-code, commit, or echo the value — inject it via environment variable and check only that it's set, not its value.
