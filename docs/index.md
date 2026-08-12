---
title: "Getting started with Pydantic Logfire"
description: "Logfire is Pydantic's end-to-end AI engineering platform for seeing what your agents, services, applications, and hosts are doing. Pick a quickstart and send your first trace."
---

# Getting started with Pydantic Logfire

Logfire is Pydantic's end-to-end AI engineering platform. It shows you what your agents, services, applications, and hosts are actually doing: every LLM call, request, and query, and how long each one took. Built on OpenTelemetry (OTel), the open standard for traces, metrics, and logs, it spans your whole stack, from AI agents to the databases and servers behind them.

New here? [Create a free account](https://logfire.pydantic.dev/login), then pick a starting point below, or follow a [guided path for your role](get-started/choose-your-path.md).

## Quickstarts

<AgentSetup>

````text
Note for the agent: This prompt was copied from the Pydantic Logfire website by the user. The user may not have read it. Briefly tell the user what you plan to do before each step, and keep them updated on progress so that this process feels responsive. Follow the steps in the order presented here where possible, e.g. install and authenticate before touching code. This includes only reading links at the appropriate time. If you have lightweight task management tools available such as a todo list, use them to help you stay on track and follow all the steps correctly. Create tasks up front where possible, including at the very start of this process, and also add/adjust them as you go based on what happens. Bias towards tracking many fine-grained detailed tasks. Do not create a plan that requires user approval. This prompt focuses on a happy path, adjust as needed.

When told to say something to the user, stick to the given wording as closely as is sensible, making adjustments based on notes in angled brackets.

Set up Pydantic Logfire in this project to instrument it and send OpenTelemetry signals to Logfire.

Check if version control is being used. If so, and if there are uncommitted changes, ask the user to commit or stash them before proceeding. If things are clean, open a new branch for the Logfire setup work. Then commit changes as you go. Each commit should be a small, self-contained change, e.g. separate dependency management from code changes.

Fetch reference material as text rather than using visual browser tools. Don't try using the Logfire UI.

If there are multiple services in this codebase, instrument them all, one by one.

Links starting with `https://logfire.pydantic.dev/-/redirect/latest-project/...` redirect to a project which is not always the one the user is working on. If you know that the user is using the EU region, change the domain to `https://logfire-eu.pydantic.dev/...`. If you know which organization and project the user is working with, use `https://logfire-<region>.pydantic.dev/<organization>/<project>/...` instead. If you don't know, this is a thing to check if the user reports these links not working well for them.

Check which languages and package management tools are being used and install the appropriate SDK:
- Python: install `logfire[system-metrics]` via uv, pip, etc
- JS/TS: install via npm, yarn, etc:
    - Node.js: `@pydantic/logfire-node`
    - Browser: `@pydantic/logfire-browser`
    - Cloudflare Workers: `@pydantic/logfire-cf-workers` and `logfire`
- Rust: `cargo add logfire`
- Other languages: There's no dedicated Logfire SDK. Install the OpenTelemetry SDK and follow https://pydantic.dev/docs/logfire/guides/alternative-clients/ to configure it to send to the Logfire backend.

Authenticate. Keep any token out of replies, logs, and committed files.
- If `LOGFIRE_TOKEN` is already set in the environment, you don't need to do anything, the SDK will use it automatically.
- Otherwise, for a local interactive Python project, say:
"""
Run this from the project folder:

```bash
logfire auth && python -c 'import logfire; logfire.configure()'
```

The first command will open a browser where you can sign in or create a free Logfire account (no credit card required) and link this machine to that account.

The second command will link this specific folder to one new or existing project in your account.

Then tell me when you're done.
"""
(Tweak the command to ensure the correct Python interpreter is used, e.g. with `uv run`.
The first command will create a file `~/.logfire/default.toml`, the second will create a gitignored folder `.logfire` in the project folder containing credentials that the SDK can read. You can check these to troubleshoot but assume they exist if things go well. Don't expect them to set `LOGFIRE_TOKEN`, this is a different kind of authentication.)
- For another language, a non-interactive shell, or a deployment, ask them to open [Logfire write-token settings](https://logfire.pydantic.dev/-/redirect/latest-project/settings/write-tokens) to create a write token. Set it as `LOGFIRE_TOKEN` in the shell environment the app runs in (e.g. `export LOGFIRE_TOKEN=...` in the terminal, or via the deployment platform's secret manager). If the project already loads a `.env` file at startup, you may store it there instead, but confirm dotenv loading is in place and the file is gitignored first. Never commit the token or print it in a reply or log output.
- If there's still problems, offer troubleshooting help, but also add "If you want to learn more yourself, try looking at [Logfire setup](https://logfire.pydantic.dev/-/redirect/latest-project/settings/setup) or the [first trace guide](https://pydantic.dev/docs/logfire/get-started/first-trace/)."

Try running `logfire whoami` or `uvx logfire whoami` (depending on what's installed) to check the state of authentication. It should work with both `LOGFIRE_TOKEN` or the credentials files created by the CLI. This should print out a URL for a specific project which you can use going forward instead of the generic redirect URL.

Run `curl https://raw.githubusercontent.com/pydantic/logfire/refs/heads/main/logfire/.agents/skills/logfire-instrumentation/SKILL.md` and read the instructions. Then read the linked references for the applicable languages. Add a few lines of code to configure the SDK and instrument web frameworks, databases, LLMs, and HTTP clients where integrations already exist. Include a service name in the configuration, but not a service version or environment. For Python projects, add `logfire.instrument_system_metrics()`, and if they're using standard logging, add `logfire.LogfireLoggingHandler()` to the logging handlers. Do not refactor unrelated code or make extensive changes. The goal is to get some observability quickly and easily. If no integrations apply, sprinkle in up to 5 manual `logfire.span/info/instrument` calls. Install dependencies as needed in a persistent manner, e.g. `uv add` rather than `pip install` for Python. Prefer Logfire extras, e.g. `logfire[fastapi]` over `opentelemetry-instrumentation-fastapi`.

Run the code. It may print a Logfire project URL, e.g. https://logfire-us.pydantic.dev/myorganisationname/myprojectname. If not, try running `uvx logfire whoami` which should pick up `LOGFIRE_TOKEN` or other credentials, even if the user's project doesn't use Python. If that doesn't give a URL, go with https://logfire.pydantic.dev/-/redirect/latest-project/. If you don't see any errors about failing to send data, assume it's working. Say "Open the [Live View](<URL>) and confirm that you see traces.". Don't try to verify yourself.

Once the user confirms that they see traces, say:

"""
Here's a link to create a PR with the changes:

<Provide a link as appropriate from GitHub or whatever. Make sure the changes are pushed. Fallback to providing CLI commands that are expected to work if no such link is possible. Skip this part if unsure or not applicable. Do not create a PR yourself unless requested to.>

Here are some things you can try instantly:

- Open [Dashboards](https://logfire.pydantic.dev/-/redirect/latest-project/dashboards/new) ([docs](https://pydantic.dev/docs/logfire/observe/dashboards/#standard-dashboards)) and enable the following standard dashboards: <1>
- Open [Services](https://logfire.pydantic.dev/-/redirect/latest-project/services) ([docs](https://pydantic.dev/docs/logfire/observe/services/)) for a quick overview of your services. <Only if multiple services were instrumented>
- Open [your service](https://logfire.pydantic.dev/-/redirect/latest-project/services/<service_name>) ([docs](https://pydantic.dev/docs/logfire/observe/services/)) for a quick overview of your service. <Only if only one service was instrumented, replacing `<service_name>` with the actual service name configured>
- Open [Hosts](https://logfire.pydantic.dev/-/redirect/latest-project/hosts) ([docs](https://pydantic.dev/docs/logfire/observe/hosts/)) to see system metrics of each of your hosts. <Only suggest this if `logfire.instrument_system_metrics()` was called.>

And here are some possible next steps I can help you with to get more out of Logfire:

1. Install the Logfire plugins, skills, and MCP server matching this coding agent.
2. Setup auto-tracing to trace every function call in your application (with a duration threashold) to get deep observability into every part of your code. <Only suggest this if using Python>
3. Add more integrations to trace libraries that you use.
4. Add targeted spans and logs customised to your code.
5. Set up dashboards in your project.
6. Set up alerts in your project.
7. Set up evaluations of your AI tasks. <Only suggest this if the application uses AI>
8. Set up prompt management for your AI tasks. <Only suggest this if the application uses AI>

Respond with the numbers that you're interested in, or let me know if you want to do something else.
"""

Remember to adjust the project redirect URLs if possible.

Replace <1> with a bulleted sublist of dashboard names based on the integrations you added:
- "Usage Overview" and "Exceptions" always
- "Web Server Metrics" if a web server integration was added
- "Basic System Metrics (Logfire)" if `logfire.instrument_system_metrics()` was called
- "LLM Tokens and Costs (from records)" if an AI integration was added

Depending on their responses to the numbered list above:

1. Read https://pydantic.dev/docs/logfire/guides/mcp-server/. For Claude Code and Codex, give the appropriate commands to copy and run in a `bash` triple backtick fenced code block. For other agents, edit the appropriate config files. If you don't have permission to edit directly, try to give a copyable command which does so. Otherwise, give plain instructions.
2. Read https://pydantic.dev/docs/logfire/instrument/add-auto-tracing/. Make the appropriate edits in an isolated commit to instrument the application code, not libraries. Use `min_duration=0.01`. Summarise the changes and their implications and point them to the docs.
3. If using Python, run `logfire inspect` to see which integrations exist for installed modules, then set those up. Next, regardless of language, investigate what libraries the project uses. Browse the docs for integrations which apply. Then search the web for OpenTelemetry instrumentations for libraries that don't have a Logfire integration.
4. Add calls to `logfire.span/info/error/exception/instrument` where appropriate.
5. You'll need the MCP server to create/edit dashboards yourself. Read https://pydantic.dev/docs/logfire/observe/write-dashboard-queries/.
6. You'll need the MCP server to create/edit alerts yourself. Read https://pydantic.dev/docs/logfire/observe/alerts/.
7. Read https://pydantic.dev/docs/logfire/evaluate/overview/ to start.
8. Read https://pydantic.dev/docs/logfire/prompt-management/ to start.
````

</AgentSetup>

<div class="grid cards" markdown>

- <span class="lf-icon lf-icon--trace"></span> [__Send your first trace__](first-trace.md)

  Install the SDK and watch a trace arrive in the Live view, in about 5 minutes.

- <span class="lf-icon lf-icon--metrics"></span> [__Monitor your infrastructure__](guides/web-ui/hosts.md)

  Monitor hosts, Kubernetes, and cloud infrastructure alongside your application.

</div>

## Explore

<div class="grid cards" markdown>

- <span class="lf-icon lf-icon--agent"></span> [__Understand agent observability__](ai-observability.md)

  See how one trace connects an agent's model calls, tools, and the services behind them.

- <span class="lf-icon lf-icon--live"></span> [__Watch it live__](guides/web-ui/live.md)

  See traces and logs stream in, and drill into any span to read its full detail.

- <span class="lf-icon lf-icon--sql"></span> [__Query with SQL__](guides/web-ui/explore.md)

  Slice your data with the SQL you already know, not a proprietary query language.

- <span class="lf-icon lf-icon--dashboards"></span> [__Dashboards and alerts__](guides/web-ui/dashboards.md)

  Chart what matters and get notified in Slack when it changes.

- <span class="lf-icon lf-icon--evals"></span> [__Evaluate and ship AI features__](evaluate/overview.md)

  Run evaluations, manage prompts, and route models through the AI gateway.

- <span class="lf-icon lf-icon--metrics"></span> [__Metrics explorer__](guides/web-ui/metrics-explorer.md)

  Browse the metrics you're sending and break any of them down by dimension, no SQL required.

- <span class="lf-icon lf-icon--integrations"></span> [__Integrations__](integrations/index.md)

  FastAPI, Django, SQLAlchemy, HTTPX, and 40+ more, each with one line of setup.

</div>

## New to observability?

[Core concepts](concepts.md) explains spans, traces, and logs, and how to read them in Logfire. [Read why Logfire exists](why.md).
