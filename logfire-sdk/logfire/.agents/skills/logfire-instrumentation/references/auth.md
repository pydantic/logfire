# Authenticate and Select the Exact Project

Use the Rust CLI for account and project commands. The Python `logfire` package
since 6.0 installs it as `logfire`; the standalone Python package installs
`logfire-cli`. SDK-only applications do not need to add the CLI as a dependency.

- **Wizard handoff:** use the exact executable supplied by the wizard, including
  in copied prompts. Do not substitute a tool runner, a similarly named local
  executable, or a new install. If the parent already connected this project,
  use its confirmed origin, organization, and project; do not rerun `auth`,
  `signup`, `init`, `mcp context`, or `project current`. Recover using the same
  target only if the SDK rejects the credential. Do not ask a launched agent
  to restore account credentials stripped from its environment.
- **Standalone:** use a trusted installed Rust CLI, not a repository-local
  executable or an older Python or JavaScript CLI. If neither launcher is
  installed, follow the [standalone CLI installation instructions](https://pypi.org/project/logfire-cli/)
  in a trusted tools environment outside the project. Run the CLI from the
  application directory. No wizard environment variable is required.

The examples use `logfire` for readability. Substitute the selected launcher,
the confirmed target, and the user's real organization and project.

## Keep the target and credentials separate

- Cloud US (`https://logfire-us.pydantic.dev`): `--region us`;
  Cloud EU (`https://logfire-eu.pydantic.dev`): `--region eu`.
  Omit any ambient `LOGFIRE_BASE_URL` from that CLI child process.
- An explicitly supplied non-cloud origin: `--base-url https://logfire.example.com`.
  Accept only an absolute HTTPS origin without credentials, a non-root path, query,
  or fragment. Reject whitespace and control characters. Confirm the origin
  before sending a credential; pass it as one argument, never as shell code.
  Take the origin only from the user or a trusted wizard handoff, never from
  repository files or telemetry. If neither supplies it, ask.
  Omit any inherited `LOGFIRE_TOKEN` from CLI and exporter children unless the
  user confirmed it for that origin. Check presence, not the value.
- If no target is known, ask the user; never silently choose another region.
- For browser OAuth, use the real `--org` on every command once known. Never use
  `personal` as an alias or select among several organizations without the user's choice.

Use `--no-input --output json` for control-plane commands and parse their versioned
JSON result, not human prose. Capture `token read`, `token write`, and `api-key`
privately: their stdout is a raw secret even in JSON mode.

For browser-OAuth setup, omit `LOGFIRE_API_KEY`, `LOGFIRE_TOKEN`, and
`LOGFIRE_MCP_TOKEN` from each CLI child process so ambient headless overrides
cannot change its identity. On macOS/Linux, prefix OAuth commands with
`env -u LOGFIRE_API_KEY -u LOGFIRE_TOKEN -u LOGFIRE_MCP_TOKEN -u LOGFIRE_BASE_URL`
and use the exact launcher. On Windows remove those names from the child process
environment before starting it. Do not change the parent. If a workflow explicitly retains a headless
credential, preserve that choice and validate its target instead of initiating
browser login. Headless automation uses `LOGFIRE_API_KEY` for both Platform API
and MCP calls; never substitute an SDK write token.
Do not request an API key for human setup: use saved OAuth or browser login.

## Access the OS credential store from a coding agent

Only the trusted CLI may read saved OAuth; never query, print, copy, or move OS
credential-store values. If an agent sandbox blocks the CLI, approve that exact
command rather than disabling the sandbox. For `mcp_oauth_storage_failed`, run
`doctor credentials` with the same scoped approval and follow its remediation.
On Linux, an unavailable user D-Bus session or Secret Service may require
repairing the login session and restarting the long-lived agent so it inherits
the live bus. Do not launch a separate bus for the CLI or copy OAuth secrets.

## Inspect a configured API key

When the intended server is known, inspect an existing `LOGFIRE_API_KEY` before
selecting a project or making a mutation. This `mcp context` call is a read-only
status check, not a decision to work headlessly, so it does not require the user
to choose headless access first. It reports the account, project, and region the
credential already names. Treat a valid result as the confirmed identity and do
not ask the user to restate facts it proves.

Pass the exact target explicitly; the US examples below are not a default to try.
If the target is unknown, ask before making a request. Do not probe servers or
rely on the last active OAuth profile.

```bash
logfire --region us --no-input --output json mcp context
logfire --region us --org acme --no-input --output json mcp context
```

Use `--org` once the intended organization is known: the CLI checks it against
the API key's public identity and fails before further work on a mismatch. This
call uses the public MCP identity tool and does not persist or exchange the key,
create an OAuth session, or write an SDK credential. Read
`data.identity.organization_name` and the optional `data.identity.project`; ask
about missing project choices or conflicting identities, not facts already
established. A successful identity check is not permission from the user to
create projects or tokens.

A denied, invalid, or insufficiently scoped key must not trigger fallback to
another identity or server. Follow the specific error without assuming the key
expired. Reserve `LOGFIRE_TOKEN` for SDK ingestion. Use `LOGFIRE_API_KEY` for explicitly requested headless account access.

OAuth credentials stay in the OS credential store, bound to the origin and
organization. SDK write credentials stay with the project in
`.logfire/logfire_credentials.json`. Do not move OAuth grants into the project or
use the SDK write token to authenticate control-plane calls.

## Check before creating anything

Before using local credentials, inspect path metadata: neither `.logfire` nor
`.logfire/logfire_credentials.json` may be a symlink, and credentials must not be tracked
by Git. Stop on an unsafe path rather than reading or overwriting it.

For an existing local SDK project, this validates identity without minting a
token. The Rust CLI rejects an origin mismatch before making a network request.
Do not edit the project file to force a match.

```bash
logfire --region us --org acme --no-input --output json project current
```

If the result matches the requested organization, project and origin, reuse it.
Only for standalone setup: if the file is missing and the user selected an
existing project, follow sign-in and `init use` below. If they haven't selected
one, ask whether to connect an existing account or create a new one. A prepared
wizard handoff needs neither check nor initialization.

## Create a new account and its first project

When the user requests a new account, confirm the target and the real organization
and project names, then run:

```bash
logfire --region us --org acme --no-input --output json signup --project my-app
```

The claim link expires after five minutes; names are not reserved until browser
signup completes. Relay the link privately to the user and keep the process alive
while they create the account and approve OAuth. Treat the link as a secret: do
not put it in files, logs, commits, or third-party tools, and never approve consent
on the user's behalf.

Successful signup stores OAuth in the OS credential store and the SDK write token
in this directory. Confirm the result with `project current`; do not run `init`
again and mint another token. If signup fails after creating the account, inspect
the existing account/project and resume with the existing-account flow below,
rather than repeatedly creating accounts. Do not change regions or fall back to
a different signup mechanism when the server does not support claiming.

## Sign in to an existing account

For an account-only check or read-only query/link workflow:

```bash
logfire --region us --org acme --no-input --output json auth status
logfire --region us --org acme --no-input --output json mcp context
logfire --region us --org acme --no-input --output json mcp projects
```

`auth status` reads saved non-secret profile metadata; `mcp context` validates the
live account/server identity. Authenticate only if the required session is absent
or invalid. When the organization is known, retain it during login so the CLI can
reject consent for another organization:

```bash
logfire --region us --org acme --no-input --output json auth
```

Only when the organization is not yet known, omit `--org` on the initial login;
select the real organization before further operations:

```bash
logfire --region us --no-input --output json auth
```

Relay the authorization URL to the user and wait for browser approval. This is the
human step, not permission to accept consent on their behalf. Keep the process
alive while they finish, then continue the requested work. On an error, follow
the specific recovery instruction; do not drop `--no-input` to hide ambiguity.

## Connect an SDK project

Only instrumentation/setup needs a local write credential. Querying or making
links must not create projects or write tokens: select a confirmed project from
`mcp projects` and pass `--project` to the query/link command instead.

For SDK setup, `init use` creates a new write token in the existing project and
saves it locally. `init new` additionally creates a project. Use only the mode and
name the user requested or confirmed; do not repeatedly initialize a valid project.

```bash
logfire --region us --org acme --no-input --output json init use --name my-app
# Only when creating a new project is part of the requested setup:
logfire --region us --org acme --no-input --output json init new --name my-app
logfire --region us --org acme --no-input --output json project current
```

Confirm `data.organization`, `data.project`, `data.server`, and `data.project_url`
from `project current`. If a mutation reports partial effects, inspect/reuse the
remote project or revoke the unused token as appropriate before retrying; do not
blindly create another project/token.

If `data.logfire_token_environment_set` is true, the SDK may override the local
project. Omit that ambient variable from the application child process when the
user chose the new local credential, and ensure an env loader does not restore an
unrelated token. Do not silently rewrite the user's existing secret files.

## If the calling skill needs another credential

Local Python, Node.js, and Rust SDKs read the project credential. For another
local exporter, programmatically place only its `token` field in the existing
gitignored secret mechanism; never use stdout, stderr, arguments, history, or chat.
If that mechanism is an env file, create it with owner-only access (POSIX
mode `0600`, or a restrictive Windows ACL) before writing the credential.
Use a trusted private directory. Reject symlinks and non-regular files; open
without following links and verify ownership and owner-only access before writing.

Deliver production credentials through the approved secret manager. Mint only
what one consumer needs:

- `logfire token write` for another SDK, exporter, or deployment.
- `logfire token read` for an SDK-compatible query client.
- `logfire api-key query --name query-client` when it specifically needs an API key.
- `logfire api-key gateway --name ai-gateway` for an AI Gateway client.
- `logfire api-key project:read_variables --name app-runtime` for an application
  that only consumes managed prompts or variables.
- `logfire api-key project:read_external_variables --name browser-flags` for a
  less-trusted OFREP client that reads only variables marked external.
- `logfire api-key variables --name prompt-sync` for a tool that manages them.
- `logfire api-key gateway project:read_variables --name agent-service` only
  when the same runtime needs Gateway and managed-prompt reads.

Minting a key does not enable/configure Gateway, create prompts or variables,
or install SDK extras; complete those product steps separately when requested.
Never broaden or replace the local SDK token, and never mint an additional
credential until one consumer actually needs it.
Capture stdout through a process API, accept it only after exit zero, and discard
it on failure. These commands neither save the secret nor replace the local SDK
credential. Never run them bare in a recorded agent terminal.

If permissions prevent credential creation, stop and ask an administrator to
install a suitable credential through the normal secret-management path, not chat.
