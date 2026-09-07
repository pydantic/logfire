# Authenticate and Select the Exact Project

Shared by all three Logfire setup skills (instrumentation, infrastructure, evals) — whichever skill you're following, run this once per session; a later skill's own `whoami` check will report "already resolved" and can be skipped.

Choose the CLI target before assuming anything needs to happen. Logfire Cloud is the normal customer path and uses a region. Derive the target from the exact supplied origin and use the same target on every CLI command in this session:

- `https://logfire-us.pydantic.dev` -> `--region us`
- `https://logfire-eu.pydantic.dev` -> `--region eu`
- An explicitly supplied non-cloud Logfire origin -> `--base-url <exact-origin>`. Customer-facing, this means an on-prem Logfire deployment.

Never pass both, and never replace a Logfire Cloud region with `--base-url`. Parse a supplied URL with a standard URL parser and accept only an absolute origin: scheme, valid hostname or IP literal, and optional port, with no userinfo, non-root path, query, fragment, whitespace, or control characters. Normalize only a trailing `/`. Require `https://` for a non-cloud origin because CLI authentication sends a user credential to it. If parsing or validation fails, or the origin uses HTTP, stop and ask for a valid HTTPS origin instead; do not authenticate. Before contacting a non-cloud origin, check only whether `LOGFIRE_TOKEN` is set; never read its value. If it is set, prevent every CLI command in this session from inheriting it (for example, prefix the command with `env -u LOGFIRE_TOKEN`) unless the user explicitly confirms that token belongs to the exact origin. Do not edit the user's stored environment to do this. After `projects use`, the CLI can use the project credential it created on disk while the unrelated ambient token remains excluded. Pass a non-cloud origin as one quoted `--base-url` argument; never concatenate it into shell text or use `eval`. Do not otherwise rewrite, shorten, or guess it. In the commands below, replace `<target>` with the validated selector (`--region us`, `--region eu`, or `--base-url '<canonical-origin>'`). If the request contains no URL and there is no trustworthy region context, omit `<target>` from the initial check; a non-interactive `auth` attempt will print the available region-specific command(s) rather than silently choosing one.

Check first:

```bash
uvx logfire --non-interactive <target> whoami
# or, JS/TS project with no Python tooling: npx logfire <target> whoami (no --non-interactive)
```

If that already reports the right project and resolved target (`--region` for Logfire Cloud or `--base-url` for an explicitly supplied on-prem origin), you're done — skip straight to the rest of whichever skill sent you here, even if you haven't run `auth` yourself yet. Signing in doesn't have to be your action: the user may have done it in a browser tab left over from an earlier session, or in parallel while you were working on something else. Treat it as good news, not something to question — never undo or re-authenticate over a session that's already valid. Otherwise, run the CLI yourself from the application directory, prefixed with `uvx` or `npx` (whichever is available) — it's a setup tool, not an app dependency. Both are real, maintained CLIs (the JS one lives in `pydantic/logfire-js` and ships to npm as the bare `logfire` package) with near-identical commands — but they are not flag-identical:

- **`--non-interactive` is Python-CLI-only right now.** The JS CLI (`npx logfire`) doesn't recognize it and errors with "Unknown option" if you pass it — omit it entirely on every `npx logfire` invocation below; keep it on every `uvx logfire` one.
- **If `npx logfire <anything>` — including `--help`, or a name you made up — exits 0 with zero output**, that's a stale global npm install of `logfire` from before v0.21.9 shadowing the fetch (a real, now-fixed bug: invoking the published bin through a symlink, which is exactly how npx and global installs both work, made the entrypoint check fail silently). Check with `npm ls -g logfire`; if it reports a version below 0.21.9, uninstall it (`npm uninstall -g logfire`) so `npx` fetches current instead of using the stale global one, or use `uvx` for this step instead.

```bash
# Python CLI (uvx logfire) -- always include --non-interactive:
uvx logfire --non-interactive <target> auth
uvx logfire --non-interactive <target> projects list --json
uvx logfire --non-interactive <target> projects use <project-name> --org <organization-name>
uvx logfire --non-interactive <target> whoami

# JS CLI (npx logfire) -- same commands and flags, but drop --non-interactive entirely:
npx logfire <target> auth
npx logfire <target> projects list --json
npx logfire <target> projects use <project-name> --org <organization-name>
npx logfire <target> whoami
```

**On the Python CLI, always put `--non-interactive` immediately after `logfire`, on every invocation, for the rest of whichever skill sent you here too.** Without it, a question with nobody to answer it (which org? which project?) blocks on a read that never returns — there's no TTY for the CLI to notice is missing, so it can't detect this on its own. It's the only way to guarantee a clear error instead of a silent hang. The JS CLI doesn't have this flag yet; if a JS-CLI command needs to ask something (e.g. which account, when more than one token is cached) with no TTY attached, it fails with a clear "not running in a terminal" error instead of hanging — so the outcome is the same either way, just reached differently.

- `<target>` is a global option: put it after `--non-interactive` on Python commands and immediately after `logfire` on JavaScript commands, before the subcommand. The product prompt only needs to supply the exact Logfire URL; this reference owns the `--region` versus `--base-url` distinction.
- `auth` with `--non-interactive` does **not** open a browser — it prints a URL and polls for you to finish. Relay that URL to the user; don't wait silently.
- `projects list --json`: exactly one project returned? Use it. Several plausible and none identified? Ask the user. None exist? `uvx logfire --non-interactive <target> projects new <project-name> --org <organization-name>` instead (JS: `npx logfire <target> projects new <project-name> --org <organization-name>`).
- Any command failing with `NonInteractiveError` explains what to do next in its own message — usually the exact missing flag (commonly `--org`), but `auth` with no region instead prints a runnable `--region <id> auth` line per region. Follow what the message says and retry once. Don't drop `--non-interactive` to make the error go away; that trades a clear message for the hang it exists to prevent.
- `whoami`'s org/project/region is what every later step must match — instrumentation, verification, any link you give the user. Never substitute a different or "latest" project.
- If both `.logfire/` credentials and `LOGFIRE_TOKEN` are present, `LOGFIRE_TOKEN` wins silently — `whoami` reports whichever is actually in effect. If they'd point at different projects, fix or unset the one you don't want before continuing.
- Never print, log, hard-code, commit, or echo a token, and don't read `~/.logfire/default.toml`'s contents — a bad or missing credential surfaces as a CLI error, not a prompt. The one exception is reading `.logfire/logfire_credentials.json`'s `token` key programmatically, and only to hand it to a non-native-SDK application language that needs the actual value (see below) — never to print, display, or otherwise surface it.

## If the calling skill needs a write token, not just a CLI session

Some callers need an actual token value, not just an authenticated CLI session. `projects use` creates a project-scoped write token and stores it in the gitignored `.logfire/logfire_credentials.json`; do not mint a second token merely because a non-SDK process needs the value:

- **A setup with no Logfire SDK reading local credentials for it** needs a write token for its OTLP exporter's Authorization header. Check the language's own instrumentation reference for whether its SDK already handles this. When nothing does, reuse the credential `projects use` created: read only the `token` key programmatically and write it directly into the runtime's existing gitignored local secret mechanism, without sending the value to stdout, stderr, shell history, source control, or chat.
- An **OpenTelemetry Collector** can use that same CLI-created write token. For Docker or a local host, write a mode-`0600`, gitignored env file such as `.logfire/logfire.env` and configure the Collector to load it. For Kubernetes, create or update the Secret from that env file with `kubectl create secret generic logfire-token --from-env-file=.logfire/logfire.env --dry-run=client -o yaml | kubectl apply -f -`; the dry run emits the manifest directly to `apply` without persisting or displaying an intermediate secret. Use the deployment's secret manager instead when one already exists.
- If `projects use` cannot create the credential because the authenticated user lacks `write_token` permission, stop and ask a project administrator to provide or install an appropriate credential through their normal secret-management path. Never ask anyone to paste a token into the agent chat.
- An **API key** for `LogfireAPIClient` (hosted-dataset push/pull) comes from **Settings → API Keys**, scoped `project:read_datasets`/`project:write_datasets` — a generic write/read token lacks those scopes.

Same rule applies to all three: never print, log, hard-code, commit, or echo the value — inject it via environment variable and check only that it's set, not its value.
