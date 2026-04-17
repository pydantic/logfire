# PRP 15: Prompt Management — Documentation Structure

## Goal

Define the structure, page-by-page content, and drafting sequence for customer-facing documentation of Prompt Management. The structure must reflect the product as it actually ships — not as the `petyo/prompt-management` branch is currently implemented — so several pages are blocked on the product changes captured in [`prompt-mgmt-release-concerns.md`](./prompt-mgmt-release-concerns.md).

After this PRP:

- there is a clear outline of what pages exist and who each one is for
- each page has a brief describing content, must-include points, and claims that must **not** be made yet
- the drafting sequence is ordered so writers start with pages whose truth does not depend on unresolved code decisions
- planning artifacts (this PRP, `meta-plan.md`, `variables-backing-pivot.md`, prior PRPs) are explicitly marked as non-customer material and are not referenced from the customer docs

## Why

- The feature is backed by a non-trivial data model (prompts as `kind='prompt'` rows in `variable_definitions`, versioned templates, autosaved settings, scenarios, runs) that does not map onto a typical "prompt library" mental model. Docs have to teach the model, not just list APIs.
- Three audiences consume this feature differently: prompt authors in the UI, SDK integrators in application code, and project admins who configure gateways and permissions. A single linear doc does not serve them.
- Several concerns from the pre-release review affect what can be truthfully written today. The structure below is explicit about which pages must wait.

## Audiences

Three entry points, three different first pages:

- **Prompt authors** (PMs, prompt engineers): land on the Guides section; want "Create your first prompt" and "Ship a prompt to production".
- **SDK integrators** (app developers): land on the SDK guide; want payload shape, grammar, and a working code sample.
- **Project admins**: land on Administration; want plan/gateway prerequisites, permissions, and feature enablement.

## Structure

```
Prompt Management
├── 1. Overview
│   ├── What it is
│   ├── How prompts relate to Managed Variables
│   └── When to use prompts vs. the Playground
├── 2. Concepts
│   ├── The four nouns: prompts, versions, scenarios, runs
│   ├── Identifiers: display_name, slug, internal name
│   ├── What a version freezes (template only)
│   ├── Autosaved settings vs. versioned template
│   ├── Template variables and the {{prompt}} reserved variable
│   └── Anatomy of a scenario (messages, parts, tool calls/returns)
├── 3. Guides (task-oriented)
│   ├── Create your first prompt
│   ├── Write templates with variables
│   ├── Define scenarios (system/user/assistant/tool turns)
│   ├── Run a prompt against a single scenario
│   ├── Run a prompt across a dataset (batch run)
│   ├── Save, compare, and promote versions
│   ├── Configure tools for a prompt
│   ├── Ship a prompt to production (cross-surface workflow)
│   └── Use prompts from your app via the SDK
├── 4. Template reference
│   ├── Supported grammar (exact, closed set)
│   ├── Variable naming rules
│   ├── Reserved variables ({{prompt}})
│   └── Error messages
├── 5. API & SDK reference
│   ├── SDK: fetching prompts via /v1/variables
│   └── Payload shape (kind='prompt', template-only version contract)
├── 6. Administration
│   ├── Enabling the feature
│   ├── Plan requirements
│   ├── Gateway setup
│   ├── Permissions model
│   └── Naming strategy
└── 7. Known limitations & roadmap
```

## Page-by-page briefs

Each brief states: who it is for, what it must contain, and any claim that cannot be made until a specific release-concern is resolved.

### 1.1 What it is
- **For:** all audiences.
- **Must contain:** one-paragraph positioning, single annotated screenshot of the prompt editor, a diagram showing the four nouns.
- **Must not:** claim block-helper template features, imply versions freeze model/tool settings, show an example that pins a version to production without crossing to the variables page.

### 1.2 How prompts relate to Managed Variables
- **For:** all audiences, especially users who already use managed variables.
- **Must contain:** honest explanation that prompt rows coexist in `variable_definitions` under `kind='prompt'`; a callout that prompts appear in both the Prompts list and the Managed Variables list; a diagram of the four responsibilities (authoring on Prompts page, rollout on Variables page).
- **Blocked on:** concern 3 read-only surfacing (**if** "Currently serving: vN" lands in Prompts UI, this diagram changes). Draft a placeholder version now; rewrite after the code lands.

### 1.3 When to use prompts vs. the Playground
- **For:** new users deciding where to start.
- **Must contain:** short decision table — Playground for one-off exploration, Prompts for anything intended to ship.

### 2.1 The four nouns
- **For:** all audiences.
- **Must contain:** prompt, version, scenario, run — one paragraph each with a small worked example. Cardinalities: 1 prompt : N versions, 1 prompt : N scenarios, 1 prompt : N runs, 1 run : N run cases.
- **Evidence:** cite `logfire_db/crud/prompts.py` types if readers want to drill in.

### 2.2 Identifiers
- **For:** anyone who will see the three names.
- **Must contain:** the three-column table from `release-concerns.md` §7 (display_name / slug / internal name). Explain the `prompt__` prefix the SDK sees today.
- **Blocked on:** concern 7 SDK helper. If `logfire.prompt(slug=...)` lands, this page collapses; the prefix becomes an implementation detail.

### 2.3 What a version freezes
- **For:** anyone who will save or pin a version.
- **Must contain:** an explicit statement that saving a version freezes the template text and nothing else. A worked example showing that changing the model between runs uses the new model on both old and new versions. A "what to do if you need the old model back" footnote pointing at run history snapshots.
- **Blocked on:** concern 2 decision. If the team adopts the two-tier "publish" model, this page rewrites substantially. Draft content now but do not publish until the versioning decision is made.

### 2.4 Autosaved settings vs. versioned template
- **For:** same readership as 2.3.
- **Must contain:** a small diagram of the two lifecycles — template updated on Save Version, settings updated immediately on every edit. A note that runs snapshot the settings at execution time, so run records are reproducible even though versions are not.
- **Blocked on:** same as 2.3.

### 2.5 Template variables and the `{{prompt}}` reserved variable
- **For:** all prompt authors.
- **Must contain:** how scenario variables are resolved; how `{{prompt}}` gets replaced by the rendered prompt inside scenario messages; rules for undefined variables.
- **Blocked on:** concern 1 grammar decision. Do not specify what features the template supports on this page until all three surfaces agree.

### 2.6 Anatomy of a scenario
- **For:** prompt authors doing tool-calling work.
- **Must contain:** message roles (system/user/assistant/tool), part kinds (text, tool-call, tool-return), and a worked multi-turn example.

### 3.1 Create your first prompt
- **For:** new prompt authors.
- **Must contain:** screenshots, not text-only. Prereqs at the top (plan eligibility, gateway configured). End-to-end walkthrough: create, write template, add one variable, define default scenario, preview, Run.
- **Blocked on:** concerns 1, 4, 5. Waits until grammar, release shape, and gateway UX are resolved.

### 3.2 Write templates with variables
- **Blocked on:** concern 1. The whole page is grammar-specific.

### 3.3 Define scenarios
- **For:** authors moving beyond single-turn.
- **Must contain:** adding system/user/assistant turns, adding tool calls and tool returns, setting scenario variables.

### 3.4 Run a prompt against a single scenario
- **For:** authors iterating on a single case.
- **Must contain:** how the Run button works, where output appears, where it is stored in run history. Cost note: each run spends gateway budget.
- **Blocked on:** concern 5 prerequisite flow.

### 3.5 Run a prompt across a dataset
- **For:** authors doing evaluation.
- **Must contain:** linking a dataset, variable column mapping, `max_cases` behavior (max 500 per call), where results land, how to view per-case output.
- **Must include** a clear cost warning — batch runs spend real budget.
- **Blocked on:** concern 6. Should not be published before a cost ceiling is added; otherwise this page is a footgun tutorial.

### 3.6 Save, compare, and promote versions
- **For:** authors going from draft to shipped.
- **Must contain:** save version flow; version diff UI (template only — call this out explicitly); where promotion happens (variables page today).
- **Blocked on:** concerns 2 and 3. If "publish snapshot" or inline label controls land, this page rewrites.

### 3.7 Configure tools for a prompt
- **For:** authors using tool-calling.
- **Must contain:** tools editor, tool schema, note that tools are autosaved (not versioned).

### 3.8 Ship a prompt to production
- **For:** any author moving from iteration to deployment. **This is the load-bearing page.**
- **Must contain:** the four-step cross-page workflow (save version in Prompts → assign label on Variables → SDK calls with label → confirm serving state). Screenshots of both surfaces. An explicit "your app still serves the old version until you assign the label" warning.
- **Blocked on:** concern 3 — should not publish until at least a read-only "Currently serving" indicator exists in the Prompts UI. Otherwise the walkthrough requires users to trust out-of-band knowledge.

### 3.9 Use prompts from your app via the SDK
- **For:** app developers.
- **Must contain:** payload shape returned by `/v1/variables/`, label-based fetching, rendering the template locally, passing rendered output to the user's model client. Working end-to-end sample.
- **Blocked on:** concerns 1, 7. Needs the rendering helper or a documented grammar contract, and ideally `logfire.prompt(slug=...)` to hide the prefix.

### 4. Template reference
- **For:** authors and SDK users needing the authoritative grammar.
- **Must contain:** closed-set list of supported tokens, with examples of supported and **unsupported** usage.
- **Blocked on:** concern 1. This page cannot exist until the grammar is one thing across all three surfaces.

### 5.1 SDK: fetching prompts
- **For:** app developers.
- **Must contain:** fetching with `logfire.var(...)` (or `logfire.prompt(...)` post-helper), the `kind='prompt'` discriminator, attempting to write back raises `PromptVariableMutationNotAllowed`.

### 5.2 Payload shape
- **For:** app developers doing schema validation.
- **Must contain:** JSON shape of `serialized_value` for prompt versions (template only, today), and the invariants the server enforces.
- **Blocked on:** concern 2. If payload widens to include settings/tools, schema changes.

### 6.1 Enabling the feature
- **For:** project admins.
- **Must contain:** plan eligibility check, current release state (Preview/GA), how to opt in if Preview.
- **Blocked on:** concern 4. Needs a coherent release shape defined first.

### 6.2 Plan requirements
- Brief page; cross-link to billing docs.

### 6.3 Gateway setup
- **For:** project admins.
- **Must contain:** gateway enablement, key creation, role-dependent paths, legacy vs. integrated distinction.
- **Blocked on:** concern 5. If the gateway prereq funnel is consolidated or inline repair lands, the page shrinks considerably.

### 6.4 Permissions model
- **For:** security reviewers and project admins.
- **Must contain:** current mapping (`read_variables` / `write_variables` gate all prompt capabilities), explicit call-out that run history is visible to all `read_variables` holders, batch-run cost implications.
- **Blocked on:** concern 6. If `read_prompts` / `write_prompts` / `run_prompts` land, this page gets a cleaner matrix.

### 6.5 Naming strategy
- **For:** admins with large variable inventories.
- **Must contain:** slug rules, hyphen/underscore collapse behavior, the `prompt__` prefix convention.
- **Blocked on:** concern 7 slug validation fix (ideally).

### 7. Known limitations & roadmap
- **For:** all audiences, referenced defensively from other pages.
- **Must contain:** honest list of current limitations (versioning scope, coarse permissions, two-place workflow, grammar status). This page is the pressure valve that lets earlier pages stay crisp.

## Drafting sequence

### Can be drafted now (not blocked on any concern)
- §1.1 Overview: What it is (placeholder diagram OK)
- §1.3 When to use prompts vs. Playground
- §2.1 The four nouns
- §2.6 Anatomy of a scenario
- §3.3 Define scenarios
- §3.7 Configure tools for a prompt
- §6.2 Plan requirements
- §7 Known limitations (this is the defensive page — can ship before product fixes)

### Can be drafted but not published until a single concern is resolved
- §1.2 How prompts relate to Managed Variables → concern 3
- §2.2 Identifiers → concern 7
- §2.3 / §2.4 Versioning and settings → concern 2
- §3.6 Save/compare/promote → concerns 2, 3
- §3.8 Ship to production → concern 3
- §5.1 SDK fetching → concern 7
- §5.2 Payload shape → concern 2
- §6.1 Enabling the feature → concern 4
- §6.3 Gateway setup → concern 5
- §6.4 Permissions → concern 6
- §6.5 Naming strategy → concern 7

### Blocked on the grammar decision (concern 1)
- §2.5 Template variables
- §3.1 Create your first prompt
- §3.2 Write templates with variables
- §3.4 Run a single scenario
- §3.5 Run across a dataset (also blocked on concern 6)
- §3.9 SDK usage (also blocked on concern 7)
- §4 Template reference

## Out of scope

- Public publication of `meta-plan.md`, `variables-backing-pivot.md`, `notes.md`, `transcript.md`, `ux-prototype-plan.md`, or any `plans/*prompt-mgmt*.md` file. These are engineering artifacts and remain internal.
- Reference documentation for `ui_api/projects/prompts.py`. The UI API is not a public surface; only `/v1/variables/` is.
- Migration guides. The feature is new; there is no prior-version migration story.
- Per-prompt permissions documentation. Not planned for v1.

## Success criteria

- Every page in the structure has a brief.
- Every brief states its blocking concern explicitly, or confirms none.
- A writer reading this PRP plus `docs/prompt-management/release-concerns.md` can decide for each page: "draft now", "draft and hold", or "wait".
- No customer-facing page makes a claim that is untrue on any of the three surfaces (editor preview, UI Run, SDK consumption) at the time of publication.
