# Prompt Management: Pre-Release Concerns

_Created: 2026-04-17_
_Status: Review input for release planning and docs effort_

This document summarizes concerns identified while reviewing the `petyo/prompt-management` branch against the goal of writing customer-facing documentation. Each concern is described with enough evidence to be actionable, and ranked by the severity of its effect on either the release or the docs that describe it. Concerns that are purely repo hygiene (stale planning artifacts, naming collisions) are intentionally out of scope here.

## TL;DR

Seven concerns, four of which should be resolved in code before any customer-facing documentation is written:

1. **Template rendering is inconsistent across three surfaces.** Editor preview uses real Handlebars, the UI Run path uses a regex, and SDK consumers have no renderer at all. Docs cannot truthfully describe what a template is until these agree.
2. **Saved versions freeze only the template.** Model, tools, and settings live in a mutable autosaved row. A pinned "version 2" can behave differently at different times.
3. **Rollout lives on one page, authoring on another.** "Which version is live?" is invisible from the Prompts UI; promoting a version requires crossing over to the Managed Variables detail page.
4. **The feature has already released to the API but not to the UI or the SDK.** Frontend is localStorage-flag-gated, backend endpoints are live, SDK lacks idiomatic helpers. The three surfaces need to land coherently before GA.
5. **Gateway prerequisites are an eight-state funnel with no inline repair.** First-run users bounce through unrelated settings pages before they can click Run.
6. **Permissions are coarse.** A single `write_variables` bit covers iterate, promote, single-run, and 500-case batch runs.
7. **Each prompt has three identifiers and the internal one leaks to SDK callers.** `display_name`, `prompt_slug`, and `name = prompt__<slug>`; SDK users must know the prefix convention.

Concerns 1–4 are release-blocking; 5–7 are ship-acceptable if docs are honest about the state, but each has product work that would pay for itself quickly.

---

## 1. Template rendering is inconsistent across three surfaces

The same template renders differently in three places.

| Surface | Renderer | Grammar honored |
|---|---|---|
| Editor preview | real Handlebars (`handlebars.create()`) — `src/app/prompts/lib/prompt-rendering.ts:1,37` | identifiers, nested paths, block helpers (`{{#if}}`, `{{#each}}`), helpers |
| UI Run / batch | regex `\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}` — `services/prompt_rendering.py:10` | literal `{{name}}` substitution; dots allowed in identifiers but not treated as nested paths |
| SDK consumer | no renderer ships; user writes their own | whatever the consumer implements (the demo hand-rolls a regex in `demo_prompt_variables_pydantic_ai.py:72-78`) |

The CodeMirror editor also uses Handlebars **syntax highlighting** (commit `9caa065777`), which asserts editor-level support for features the server does not honor.

### Why it matters

- A user writing `{{#each items}}{{name}}{{/each}}` sees per-item output in preview, then clicks Run and the model receives the raw `{{#each items}}…{{/each}}` literal. No error, no warning.
- `{{user.name}}` has two incompatible meanings: nested lookup in the frontend, flat identifier `user.name` on the backend.
- `scenario_variables: dict[str, str]` at the schema layer (`PromptDraftRunRequest`) rules out the data shapes block helpers would need. The schema forecloses what the editor advertises.
- SDK consumers have no grammar contract. Every app picks its own renderer, and at least one of {editor preview, UI Run, production} will disagree with the other two.

### What needs to change

Pick a grammar and enforce it on all three surfaces. Three defensible exits:

- **Narrow everywhere to identifier substitution.** Frontend renderer drops to plain substitution; remove Handlebars highlighting. Smallest technical fix, meaningful product regression.
- **Widen backend to Handlebars.** Needs a Python Handlebars implementation (`pybars3` is unmaintained) and `scenario_variables` typed as `dict[str, JSONBData]` across the API and the inputs panel.
- **Declare grammar via a typed contract.** Publish `{ grammar: "logfire-v1" }` in prompt payloads; support a minimal grammar by default and an advanced grammar on opt-in. Most work, best long-term product answer.

Regardless of exit, two things are needed before docs:

- A shared cross-renderer fixture suite (promised in `variables-backing-pivot.md`, not yet present).
- An SDK rendering helper (e.g., `logfire.render_prompt(template, variables)`) so the canonical grammar has a reference implementation and SDK users stop inventing their own.

---

## 2. Versioning scope covers only the template

### What gets versioned

```python
# logfire_db/crud/prompts.py:910
serialized_value = _serialize_prompt_template(request['template'])
# which is:
def _serialize_prompt_template(template: str) -> str:
    return json.dumps(template)
```

`variable_versions.serialized_value` for a prompt contains the template string and nothing else.

Model, tools, `api_format`, `route`, `model_settings`, and `stream` live in `prompt_settings`, primary-keyed on `prompt_id`, overwritten on every settings change (`final_schema_logfire.sql:1749-1765`). Runs snapshot the settings that were live at execution time — but versions do not.

### Why it matters

- "Version" in competing products (Humanloop, LangSmith, PromptLayer) freezes the full callable. Here it freezes the template string only. Users pinning to "version 2" get v2's template rendered against *whatever settings are configured right now*.
- Rollback is partial. If someone sets `temperature=2.0` and production breaks, rolling back a version does nothing — the setting isn't attached.
- Any "compare versions" UI shows template diffs only. Model or tool changes are invisible.
- The SDK contract consumes this directly: `/v1/variables/` ships `{"template": "..."}`. Authoring decisions about model and tools never reach the app. The demo's `ManagedPromptPayload` declares `model`, `tools`, `api_format` as optional-with-`None` defaults and then raises `SystemExit('Gateway mode requires the prompt version to have a stored model')` at line 102 — evidence of code written against an interface that does not yet exist on the server.

### What needs to change

Three resolutions, in roughly increasing scope:

- **Document the narrow contract honestly.** Rename the concept ("template history") and remove any UI affordance that implies broader snapshotting. Smallest change, weakest product.
- **Widen versions.** Snapshot settings and tools into the version row. Breaks the autosaved-settings UX that the branch is built around.
- **Two-tier model.** Keep autosaved settings as a working scratchpad; add an explicit "publish" action that freezes everything into a version. This is where most competitors land.

Docs must in all cases state clearly that "version" in Logfire Prompts today means template only.

---

## 3. Rollout lives on a different page from authoring

Prompt-backed rows render in the Managed Variables list with explicit disclosure (`project-settings-variables.tsx:278-339`): a "Prompt" badge, status "Backs a prompt", and inline copy "Open this row here to edit values and routing. Prompt metadata stays in Prompt Management."

The disclosure is honest. The workflow it implies is the problem.

### The responsibility split

| Task | Page |
|---|---|
| Edit template / iterate on v4 | `/prompts/<slug>/` |
| Change model / tools / settings | `/prompts/<slug>/` |
| Rename / describe the prompt | `/prompts/<slug>/` |
| **Point label `production` at v3** | `/variables/prompt__<slug>/` |
| **See which version currently serves traffic** | `/variables/prompt__<slug>/` |
| **Configure percentage rollout** | `/variables/prompt__<slug>/` |

### Why it matters

The second half of the table is the entire point of versioning. Without labels, a saved version is inert — the SDK has no way to ask for it without hard-coding a numeric version. None of that lives in the Prompts UI.

A realistic "ship to production" workflow today is:

1. Open `/prompts/welcome_email/`, iterate, save v4.
2. Leave. Navigate to Managed Variables. Find `prompt__welcome_email`.
3. Move the `production` label from v3 to v4 on the values/labels tab.
4. Hope the SDK is calling with `label='production'`.

At step 1 the user thinks they have shipped. They have not — their app is still serving v3 until step 3. The Prompts UI never indicates this. The version history shows "v4 by you" with no "currently serving: v3" signal.

### What needs to change

- **Mirror serving state into the Prompts UI.** At minimum, a "Currently serving: v3" strip next to the version selector, even if editing still happens on the variables page. This is a read-only fix and addresses the worst of the concern.
- **Eventually, mirror the label controls.** Let authors promote versions from the Prompts page directly. The variables detail stays as the advanced/legacy view.

Docs independently need a "Shipping a prompt to production" page that teaches the cross-over explicitly. Without that page, the feature silently fails the first time a user tries to use versions for their stated purpose.

---

## 4. The feature has already released to the API but not to the UI or the SDK

### Gating state

- Backend routes (`ui_api/projects/prompts.py`, `/v1/variables/` with `kind='prompt'`): live, unconditional.
- Frontend: `LocalFeatureFlagProtectedRoute` on `PROMPT_MANAGEMENT`. Flag is **not** in `SHIPPED_FEATURE_FLAGS` (`useFeatureFlag.ts:29`), defaults off, toggled per-browser via localStorage.
- SDK: no idiomatic helper. Users call `logfire.var(name='prompt__<slug>', ...)` and hand-roll a renderer (per the demo).
- Database migrations: shipped with the backend; run regardless of flag state.

### Why it matters

- `VariableConfig.kind` is now a new field returned to every SDK caller, including consumers running today against prod. Strict-schema validators could break without warning.
- Anyone who figures out `/ui_api/projects/<id>/prompts/` can create real prompts in real projects while the UI still says the feature is unavailable. Rows appear in the Managed Variables list immediately.
- `LocalFeatureFlagProtectedRoute` is a per-browser toggle. There is no org-level or project-level gating. Targeted rollout (e.g., design partners) is not supported without new server-side work.
- Once migrations apply, the schema is in every project whether the UI is on or not. Back-out after any customer writes prompt data is data-destructive.

### What needs to change

Three release states must be defined and aligned before docs are written against any of them:

| State | API | UI | SDK helpers | Audience |
|---|---|---|---|---|
| Now | live | hidden | bare | internal only |
| Preview | live | opt-in | minimal documented surface | design partners |
| GA | live | default on | idiomatic `logfire.prompt(...)` | all |

Docs written today against "Now" would describe a workflow requiring a UI the user cannot open. Writing docs against "Preview" is workable if a `logfire.prompt(...)` (or equivalent) lands in the SDK first. Writing docs against "GA" requires the flag flip and ideally org-level gating.

Related: 14 `plans/2026-04-*prompt-mgmt*.md` and `docs/prompt-management/*` files live in the repo and contain engineering-internal language (pivots, acknowledged tradeoffs). Any docs-publishing pipeline should explicitly exclude these paths.

---

## 5. Gateway prerequisites are an eight-state funnel with no inline repair

`prompt-gateway-requirements.ts` resolves to one of eight terminal states: `ready` (integrated or legacy), `loading`, `query-error`, `unsupported-plan`, `gateway-disabled`, `missing-key` (no-keys or missing-token-permission), `selected-key-unavailable`, `select-key`. Each non-`ready` state suggests an action but does not provide inline repair — every recovery path requires leaving the prompt page.

### Why it matters

- First-run users bounce through 2–3 unrelated settings pages before their first Run button works.
- The `unsupported-plan` state is a marketing leak: the Prompts feature should not render in the sidebar for ineligible orgs. Showing the feature and blocking Run with "upgrade your plan" loses the evaluation.
- Two gateway systems coexist: `hasLegacyGatewayConfig` returns `ready: legacy`; users on the legacy setup never see the integrated flow. Docs must describe both, or the team picks one to deprecate before GA.
- Role-dependent copy assumes users know their role (`isOrgAdmin`, `isProjectAdmin`). Users often do not. A small "You are a {role}" line in the prerequisite card would remove most of this.
- None of this applies to the SDK path. The gateway is a UI-only dependency. Docs must draw this line sharply: Editor Run needs a Logfire gateway key; production consumption via SDK does not.

### What needs to change

Product fixes that are cheap relative to their impact:

- Inline "Create gateway key" modal on the prompt page for project admins.
- Hide the Prompts nav entry when `isGatewayPlanEligible === false`.
- Pick a gateway system (integrated vs. legacy) and start a deprecation.
- Add a user-role indicator to the prerequisite card.

Docs should defer the per-role playbook until it is clear which funnel shape ships. A single "Prepare your project for prompt runs" page must precede any "Create your first prompt" walkthrough.

---

## 6. Permissions are coarse

Every prompt route uses one of two permissions:

```python
# ui_api/projects/prompts.py — all 23+ route declarations
dependencies=[Permissions(organization=None, project=['read_variables'])]
# or
dependencies=[Permissions(organization=None, project=['write_variables'])]
```

No `read_prompts` or `write_prompts` was added; the `test_roles.py` diff is alphabetical re-sorting only.

### The conflations

| Capability | Gated by | Risk |
|---|---|---|
| View template and settings | `read_variables` | low |
| View run history (inputs, model outputs, costs) | `read_variables` | data-sensitive |
| Save a draft version | `write_variables` | low |
| Promote a version to a label (on variables page) | `write_variables` | production-sensitive |
| Execute a single run | `write_variables` | cost-sensitive |
| Execute a batch run up to 500 cases | `write_variables` | heavily cost-sensitive |

### Why it matters

- Run records include model outputs. Anyone with `read_variables` can read every response produced by the project — a permission named for config access is now gating model output data.
- "Iterate on a draft" and "promote to production" are the same bit. Competing products separate author from publisher for good reason.
- Batch runs spend real gateway budget. No cost ceiling, no approval flow, no second-confirmation. `max_cases` accepts up to 500 per call. Fat-finger incident waiting to happen.
- Existing `read_variables` assignments (granted when it meant config-read) now silently cover prompt run history. That is a blast-radius expansion without notification.

### What needs to change

None of this blocks v1 for small teams, but before GA with any enterprise messaging:

- Introduce `read_prompts` / `write_prompts` as separate permission names, even if they map 1:1 to variables today. Cheap seam for future tightening without schema migration.
- Split `run_prompts` from `write_prompts` so interns can iterate without spend.
- Add a batch-run cost ceiling (per-user or per-project daily cap) and surface it.
- Document the current scope explicitly, including the "run history is visible to all `read_variables` holders" note.

---

## 7. Each prompt has three identifiers; the internal one leaks to SDK callers

Namespace isolation between prompts and general variables is correctly enforced (`variable_definitions_prompt_identity_check` in `final_schema_logfire.sql:2110`, plus the `_validate_general_variable_name` guard at `services/variables.py:132`). Prompts and general variables cannot collide.

The cost is three identifiers per prompt:

| Field | Example | Who sees it |
|---|---|---|
| `display_name` | `"Welcome Email"` | UI title, search |
| `prompt_slug` | `welcome_email` | URL (`/prompts/welcome_email/`) |
| `name` | `prompt__welcome_email` | SDK callers (`logfire.var(name=...)`) |

The `name` is derived from the slug via `demo_prompt_variables_pydantic_ai.py:50-51`:

```python
def get_prompt_internal_variable_name(prompt_slug: str) -> str:
    return f'{PROMPT_VARIABLE_PREFIX}{prompt_slug.replace("-", "_")}'
```

### Why it matters

- The `prompt__` prefix is an internal storage convention appearing in user SDK code. The demo defines `get_prompt_internal_variable_name` as a helper users must call; that is evidence the boundary has not settled.
- `slug.replace("-", "_")` is lossy. Slugs `order-confirmation` and `order_confirmation` both derive to `prompt__order_confirmation`. The second creation attempt hits the `(project_id, name)` uniqueness constraint with an error that references a name the user never typed.
- The slug→name derivation is enforced in service code, not at the database layer. Any future change to the derivation breaks lookup for pre-existing rows.

### What needs to change

- Ship an SDK helper (`logfire.prompt(slug=...)` or equivalent) that hides the prefix. The prefix then becomes an implementation detail, not a public contract.
- Disallow either hyphens or underscores in new slugs at the input layer, so the derivation is collision-free by construction.
- Docs: one early Concepts table showing the three identifiers, which ones users touch, and which one the SDK consumes. New users need this before they can make sense of example code.

---

## Recommended sequencing

1. Pick a template grammar and make preview, Run, and SDK agree (concern 1). Ship the cross-renderer fixture suite and the SDK rendering helper.
2. Decide the release shape (concern 4): define Preview and GA states, align SDK helper, plan flag-flip timing.
3. Add "currently serving" visibility to the Prompts UI (concern 3) — read-only is enough for the first pass.
4. Decide the versioning story (concern 2) and either narrow the name or add a publish action.
5. Before GA: split permission names (concern 6), add a batch-run cost cap, hide the Prompts nav item on ineligible plans (concern 5).
6. Ship the SDK `logfire.prompt(...)` helper so the `prompt__` prefix stops leaking (concern 7).

Docs can begin drafting admin and concept pages now. Template reference, SDK usage, and "Create your first prompt" should wait until concerns 1, 2, and 4 are resolved.
