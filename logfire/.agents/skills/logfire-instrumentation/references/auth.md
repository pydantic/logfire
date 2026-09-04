# Authenticate and Select the Exact Project

Shared by all three Logfire setup skills (instrumentation, infrastructure, evals) — whichever skill you're following, run this once per session; a later skill's own `whoami` check will report "already resolved" and can be skipped.

Check first, before assuming anything needs to happen:

```bash
uvx logfire --non-interactive whoami
# or, JS/TS project with no Python tooling: npx logfire whoami (no --non-interactive)
```

If that already reports the right project and region, you're done — skip straight to the rest of whichever skill sent you here, even if you haven't run `auth` yourself yet. Signing in doesn't have to be your action: the user may have done it in a browser tab left over from an earlier session, or in parallel while you were working on something else. Treat it as good news, not something to question — never undo or re-authenticate over a session that's already valid. Otherwise, run the CLI yourself from the application directory, prefixed with `uvx` or `npx` (whichever is available) — it's a setup tool, not an app dependency. Both are real, maintained CLIs (the JS one lives in `pydantic/logfire-js` and ships to npm as the bare `logfire` package) with near-identical commands — but they are not flag-identical:

- **`--non-interactive` is Python-CLI-only right now.** The JS CLI (`npx logfire`) doesn't recognize it and errors with "Unknown option" if you pass it — omit it entirely on every `npx logfire` invocation below; keep it on every `uvx logfire` one.
- **If `npx logfire <anything>` — including `--help`, or a name you made up — exits 0 with zero output**, that's a stale global npm install of `logfire` from before v0.21.9 shadowing the fetch (a real, now-fixed bug: invoking the published bin through a symlink, which is exactly how npx and global installs both work, made the entrypoint check fail silently). Check with `npm ls -g logfire`; if it reports a version below 0.21.9, uninstall it (`npm uninstall -g logfire`) so `npx` fetches current instead of using the stale global one, or use `uvx` for this step instead.

```bash
# Python CLI (uvx logfire) -- always include --non-interactive:
uvx logfire --non-interactive --region <region> auth
uvx logfire --non-interactive projects list --json
uvx logfire --non-interactive projects use <project-name> --org <organization-name>
uvx logfire --non-interactive whoami

# JS CLI (npx logfire) -- same commands and flags, but drop --non-interactive entirely:
npx logfire --region <region> auth
npx logfire projects list --json
npx logfire projects use <project-name> --org <organization-name>
npx logfire whoami
```

**On the Python CLI, always put `--non-interactive` immediately after `logfire`, on every invocation, for the rest of whichever skill sent you here too.** Without it, a question with nobody to answer it (which org? which project?) blocks on a read that never returns — there's no TTY for the CLI to notice is missing, so it can't detect this on its own. It's the only way to guarantee a clear error instead of a silent hang. The JS CLI doesn't have this flag yet; if a JS-CLI command needs to ask something (e.g. which account, when more than one token is cached) with no TTY attached, it fails with a clear "not running in a terminal" error instead of hanging — so the outcome is the same either way, just reached differently.

- Determine the region (US or EU) from the project's URL or the user's context *before* authenticating, and pass it up front — `--region {us,eu}` is global, right after `logfire --non-interactive`, before the subcommand.
- `auth` with `--non-interactive` does **not** open a browser — it prints a URL and polls for you to finish. Relay that URL to the user; don't wait silently.
- `projects list --json`: exactly one project returned? Use it. Several plausible and none identified? Ask the user. None exist? `uvx logfire --non-interactive projects new <project-name> --org <organization-name>` instead (JS: `npx logfire projects new <project-name> --org <organization-name>`).
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
