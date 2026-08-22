# Authenticate and Select the Exact Project

Shared by all three Logfire setup skills (instrumentation, infrastructure, evals) — whichever skill you're following, run this once per session; a later skill's own `whoami` check will report "already resolved" and can be skipped.

Check first, before assuming anything needs to happen:

```bash
logfire --non-interactive whoami
```

If that already reports the right project and region, you're done — skip straight to the rest of whichever skill sent you here. Otherwise, run the CLI yourself from the application directory, prefixed with `uvx` or `npx` (whichever is available) — it's a setup tool, not an app dependency.

```bash
logfire --non-interactive --region eu auth
logfire --non-interactive projects list --json
logfire --non-interactive projects use <project-name> --org <organization-name>
logfire --non-interactive whoami
```

**Always put `--non-interactive` immediately after `logfire`, on every invocation, for the rest of whichever skill sent you here too.** Without it, a question with nobody to answer it (which org? which project?) blocks on a read that never returns — there's no TTY for the CLI to notice is missing, so it can't detect this on its own. It's the only way to guarantee a clear error instead of a silent hang.

- Determine the region (US or EU) from the project's URL or the user's context *before* authenticating, and pass it up front — `--region {us,eu}` is global, right after `logfire --non-interactive`, before the subcommand.
- `auth` does **not** open a browser itself when there's no TTY, which an agent's own environment never has — it prints a URL and polls. Relay that URL to the user; don't wait silently.
- `projects list --json`: exactly one project returned? Use it. Several plausible and none identified? Ask the user. None exist? `logfire --non-interactive projects new <project-name> --org <organization-name>` instead.
- Any command failing with `NonInteractiveError` names the exact missing flag in its message (commonly `--org`) — supply it and retry once. Don't drop `--non-interactive` to make the error go away; that trades a clear message for the hang it exists to prevent.
- `whoami`'s org/project/region is what every later step must match — instrumentation, verification, any link you give the user. Never substitute a different or "latest" project.
- If both `.logfire/` credentials and `LOGFIRE_TOKEN` are present, `LOGFIRE_TOKEN` wins silently — `whoami` reports whichever is actually in effect. If they'd point at different projects, fix or unset the one you don't want before continuing.
- Never print, log, hard-code, commit, echo, or read a token or its credentials file (`.logfire/logfire_credentials.json`, `~/.logfire/default.toml`) — each just holds a token under a `token` key, so check only whether the file exists, not its contents. A bad or missing credential surfaces as a CLI error, not a prompt.

## If the calling skill needs a write token, not just a CLI session

`logfire-infrastructure`'s Collector exporter and any use of `logfire.experimental.api_client.LogfireAPIClient` need a token minted separately from this CLI session:

- A **write token** for a Collector exporter comes from **Project Settings → Write tokens** in the Logfire UI — the CLI's own credentials authenticate you as a person, not the Collector as a data source.
- An **API key** for `LogfireAPIClient` (hosted-dataset push/pull) comes from **Settings → API Keys**, scoped `project:read_datasets`/`project:write_datasets` — a generic write/read token lacks those scopes.

Same rule applies to both: never print, log, hard-code, commit, or echo the value — inject it via environment variable and check only that it's set, not its value.
