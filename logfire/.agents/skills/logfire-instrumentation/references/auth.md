# Authenticate and Select the Exact Project

Shared by all three Logfire setup skills (instrumentation, infrastructure, evals) — whichever skill you're following, run this once per session; a later skill's own `whoami` check will report "already resolved" and can be skipped.

Before trusting repository-local credentials, inspect path metadata only: neither
`.logfire` nor `.logfire/logfire_credentials.json` may be a symlink. In a Git
worktree, `git ls-files -- .logfire` must report nothing except an optional
`.logfire/.gitignore`; a tracked credentials file or tracked `.logfire` directory
is unsafe. Stop and report the unsafe path rather than reading or overwriting it.
This metadata check is allowed before the calling skill's repository-inspection
step; do not open any application or configuration file yet.

Then check, before assuming anything needs to happen. With `uv`, use an
isolated, config-free, version-pinned environment and invoke Python in isolated
mode so repository-local packages and `PYTHONPATH` cannot shadow the CLI:

```bash
uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive whoami
```

In a JS/TS project without `uv`, use this POSIX-shell fallback. Every invocation
gets a newly created external npm prefix, so npm cannot choose a repository-local
binary. The exact package version and `--ignore-scripts` keep the reviewed CLI
artifact stable and prevent lifecycle scripts from running:

```bash
env -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ --cache "$(mktemp -d)" --ignore-scripts --script-shell=/bin/sh --node-options='' --prefix "$(mktemp -d)" exec --yes --package=logfire@0.22.5 -- logfire whoami
```

Do not use a plain `npx logfire` command or omit the external `--prefix`, fresh
`--cache`, or Node and shell overrides. The npm CLI does not support
`--non-interactive`; without a TTY it fails instead of prompting. On Windows,
install `uv` from its
[official installation guide](https://docs.astral.sh/uv/getting-started/installation/)
and use the isolated Python CLI above rather than translating the POSIX command
into a repository-local npm invocation.

If `whoami` already reports the right project and region, you're done — skip
straight to the rest of whichever skill sent you here. Never undo or
re-authenticate over a session that's already valid. Otherwise, determine the
region from the user's context or project URL before authenticating; if it is
unknown, ask rather than guessing. Then run the matching sequence:

```bash
# Python CLI
uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive --region <region> auth
uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive --region <region> projects list --json
uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive --region <region> projects use <project-name> --org <organization-name>
uvx --isolated --no-config --from 'logfire==4.41.0' python -I -m logfire --non-interactive --region <region> whoami

# JS CLI (POSIX shell)
env -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ --cache "$(mktemp -d)" --ignore-scripts --script-shell=/bin/sh --node-options='' --prefix "$(mktemp -d)" exec --yes --package=logfire@0.22.5 -- logfire --region <region> auth
env -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ --cache "$(mktemp -d)" --ignore-scripts --script-shell=/bin/sh --node-options='' --prefix "$(mktemp -d)" exec --yes --package=logfire@0.22.5 -- logfire --region <region> projects list --json
env -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ --cache "$(mktemp -d)" --ignore-scripts --script-shell=/bin/sh --node-options='' --prefix "$(mktemp -d)" exec --yes --package=logfire@0.22.5 -- logfire --region <region> projects use <project-name> --org <organization-name>
env -u NODE_OPTIONS -u NODE_PATH npm --registry=https://registry.npmjs.org/ --cache "$(mktemp -d)" --ignore-scripts --script-shell=/bin/sh --node-options='' --prefix "$(mktemp -d)" exec --yes --package=logfire@0.22.5 -- logfire --region <region> whoami
```

**On the Python CLI, always put `--non-interactive` immediately after `logfire`.**
Without it, a question with nobody to answer it can block on a read that never
returns.

- `auth` with `--non-interactive` does **not** open a browser — it prints a URL and polls for you to finish. Relay that URL to the user; don't wait silently.
- `projects list --json`: exactly one project returned? Use it. Several plausible and none identified? Ask the user. None exist? Use `projects new <project-name> --org <organization-name>` with the same verified CLI prefix instead.
- Any command failing with `NonInteractiveError` explains what to do next in its own message — usually the exact missing flag (commonly `--org`), but `auth` with no region instead prints a runnable `--region <id> auth` line per region. Follow what the message says and retry once. Don't drop `--non-interactive` to make the error go away; that trades a clear message for the hang it exists to prevent.
- `whoami`'s org/project/region is what every later step must match — instrumentation, verification, any link you give the user. Never substitute a different or "latest" project.
- If both `.logfire/` credentials and `LOGFIRE_TOKEN` are present, `LOGFIRE_TOKEN` wins silently — `whoami` reports whichever is actually in effect. If they'd point at different projects, fix or unset the one you don't want before continuing.
- Never print, log, hard-code, commit, or echo a token, and don't read `~/.logfire/default.toml`'s contents — a bad or missing credential surfaces as a CLI error, not a prompt. The one exception is reading `.logfire/logfire_credentials.json`'s `token` key programmatically, and only to hand it to a non-native-SDK application language that needs the actual value (see below) — never to print, display, or otherwise surface it.

## If the calling skill needs a write token, not just a CLI session

Some callers need an actual token value, not just an authenticated CLI session:

- **A setup with no Logfire SDK reading local credentials for it** needs a write token for its OTLP exporter's Authorization header — check the language's own instrumentation reference for whether its SDK already handles this before assuming you need to extract one. When nothing does: for local development, reuse what `projects use` already created instead of minting anything new — read the `token` key from `.logfire/logfire_credentials.json` programmatically and pass it through the runtime's own gitignored local secret mechanism (an environment variable, or a local `.env` the app already loads safely), never printing, logging, or echoing the value itself. For a deployed/production instance, mint a separate write token from **Project Settings → Write tokens** instead and use the platform's own secret manager — a long-lived service shouldn't share the same credential as your CLI session.
- A **write token** for a Collector exporter comes from **Project Settings → Write tokens** in the Logfire UI — the CLI's own credentials authenticate you as a person, not the Collector as a data source.
- An **API key** for `LogfireAPIClient` (hosted-dataset push/pull) comes from **Settings → API Keys**, scoped `project:read_datasets`/`project:write_datasets` — a generic write/read token lacks those scopes.

Same rule applies to all three: never print, log, hard-code, commit, or echo the value — inject it via environment variable and check only that it's set, not its value.
