# Documentation style guide

This is the standard every page in the public docs (`docs/`) is held to — whether a person or an AI
agent writes it. It lays out the rules we follow going forward; recent documentation work already
follows them. If a page can't pass the [pre-publish checklist](#pre-publish-checklist), it isn't done.

Read this before writing or substantially editing a docs page. Docstrings and other in-code API text
follow normal API-reference conventions and are out of scope here.

---

## 1. Who we write for

Our docs sit at the intersection of two fields — **observability** and **AI engineering** — and few
readers arrive fluent in both. Real readers include the AI engineer (strong in Python/AI, often new
to observability), the backend developer / SRE (fluent in tracing and metrics, skeptical of hype),
the platform / security engineer (evaluating whether the org can adopt and run it safely), and the
product / growth analyst (semi-technical, cares about behavior and experiments).

Above all, every page must satisfy one standard-bearer:

> A smart person, expert in *some other field*, who has just started building with AI tools.
> Motivated and capable, but not fluent in our jargon.

This reader is **not a caricature of a confused user.** They can understand anything we take one
sentence to explain. We are not writing down to them — we are refusing to lock them out with a word
we could have glossed. A specialist walking us through their own field wouldn't drop a term of art
and move on; they'd give the plain-language version the first time. We extend the same courtesy.

Two beliefs shape everything below:

- **General observability is co-equal with AI, always.** Logfire is full-stack observability *and*
  AI engineering *and* (emerging) product analytics. We never frame AI as the whole product or let
  it bury the SRE. The AI story is first-class *inside* the docs, not the frame around them.
- **We always do two things well that make docs trustworthy:** show real worked output, and give
  every setup/how-to page a real **Verify** and **Troubleshooting** section.

---

## 2. What great documentation does

1. **Describes the reader's goal, not our mechanism.** "See every request your app handles" — not
   "attach the ASGI middleware span processor." If a word names a piece of our internals, it doesn't
   belong in reader-facing copy. A feature name is never its own description.
2. **Orients before it instructs.** Every area and page opens with *what this is and why you'd use
   it* before any code or config. The reader should know they're in the right place within one
   sentence.
3. **Teaches the practice, not just the API.** For anything the reader may be new to (evals,
   LLM-as-a-judge, distributed tracing, SLOs), teach the concept and the *when* before the *how*.
4. **Is honest.** It says when *not* to use a feature, marks what's Beta, and states consequences
   plainly — especially when data leaves the machine, costs money, or can't be undone. Depth earns
   more trust than polish.
5. **Shows, doesn't assert.** "You should now see a trace with the query nested inside it" + a
   screenshot beats "provides deep visibility." A worked example with real output beats a promise.
6. **Is approachable without being dumbed down.** Precise terms stay — they're often the thing the
   reader needs to learn. The standard is about *introducing* terms, not avoiding them.
7. **Respects the reader's time.** Overviews are short and fan out. The common path comes first. No
   filler, no hype, no restating the obvious. Every sentence earns its place.
8. **Is grounded in product truth.** A page reflects the *real* UI, the *real* error messages, and
   the *real* edge cases — found by using the thing, not by reading the design doc. A doc that
   describes how the system was *meant* to behave, rather than how it does, is a bug.
9. **Leaves a picture.** After a good concept page the reader can still *picture* what it described —
   the shape of a trace, what happens when a request crosses a service boundary. Facts without a
   mental image haven't taught.
10. **Ships and iterates.** A useful page now beats a perfect page later. The one thing "iterate
    later" never excuses: **incompleteness is fine, inaccuracy is not.** A short honest page beats a
    thorough one that tells the reader to run a command that no longer exists.

---

## 3. Page types & templates

**Frontmatter on every page:** a `title` (a user goal, sentence case) and a `description` (one
sentence on what the page is for). Keep to the one convention across the set.

**The universal skeleton** every page follows:

1. **Outcome sentence** — what you'll be able to do, in the reader's terms.
2. **Orientation** — what this is / why you'd use it (and when *not* to), before any config.
3. **Prerequisites** — including where to get any value the reader needs (project, token, key).
4. **The 95% path** — the common case first, complete and runnable.
5. **Advanced / rare / dangerous variants** — below the fold, clearly labeled.
6. **Verify** — a concrete "you should now see X in Y".
7. **Troubleshooting** — the top 2–4 failure cases as symptom → cause → fix.
8. **Next steps** — a short, reasoned fan-out.

Recognize the common page shapes and give each what it needs:

- **Quickstart** — fastest path to first data; one runnable block; ends at a verify + fan-out.
- **Integration page** — what you'll capture, install, the one-line change highlighted, verify,
  troubleshooting.
- **Feature / concept overview** — 300–800 words, builds the mental model, says when not to use it,
  fans out. This is where judgment and a teaching diagram live.
- **How-to / task guide** — one job, the 95% path first, verify + troubleshooting.
- **AI-engineering page** (evals, prompts, AI observability) — teach the practice before the API;
  show real output (a printed table with real numbers, a real trace).
- **Reference** — terse, exhaustive, machine-precise: every command runnable, every name exact.

**One job per page.** Documenting two jobs is two pages. An overview that has grown a full how-to
inside it should be split.

---

## 4. Writing style

### Voice
Write like a **senior engineer explaining something to a smart peer** who happens not to know this
corner yet. Direct, warm, confident, specific. Never chummy, never hype, never condescending.

- **Second person, present tense, active voice.** "You add three lines and Logfire records every
  request." Not "Requests will be recorded by the SDK."
- **Plain and concrete over grand and vague.** "See which endpoint was slow and why" beats "gain
  deep, powerful visibility."
- **No filler and no hype** (see the banned list in §5). Emoji essentially never in body copy.

### Openings — the most important sentence on the page
The first sentence states the **reader's outcome** — not our mechanism, not a feature name, not
company backstory, not badges.

- **Do:** "See every database query your app runs — the SQL, how long it took, and which failed."
- **Don't:** "Logfire will create a span for every query executed by a SQLAlchemy engine." (mechanism)
- **Don't:** "The live view is the focal point of Logfire (as the name suggests)." (name-as-description)
- **Don't:** open with CI/PyPI/license badges or company backstory.

For an unfamiliar *practice*, name the **pain before the solution**: "Debugging an agent without a
trace is guesswork. Here's how to see exactly what it did."

### Structure
- **Front-load the 95% path.** Never lead a scrubbing page with "how to disable scrubbing" or a
  distributed-tracing page with manual context propagation.
- **Headings are user goals**, not our nouns. "Find your slowest endpoints", not "Latency facets".
- **Progressive disclosure.** Basic path up top; advanced below the fold; reference at the bottom or
  a linked page.
- **Scannable.** Short paragraphs, meaningful headings, lists for parallel items.
- **Finish the page.** Every page ends deliberately — a Verify step, Next-steps, a Troubleshooting
  list. It must never trail off mid-thought.

### Explaining terms (the core craft)
- **Define every term of art in place, at first use, in one clause** — using the [glossary](#the-canonical-glossary)
  wording so the whole set is consistent: "a span (one unit of work — a single operation, with a
  start and a duration)".
- **Spell out field-specific acronyms the first time they appear on a page.** Assume the reader
  arrived from a search; nothing is "already established" by another page: "personally identifiable
  information (PII)", "OpenTelemetry Protocol (OTLP)". Leave the acronyms the whole space already
  reads as words — AI, LLM, SDK, API, HTTP, JSON, URL, CLI. The test is whether spelling it out
  teaches the reader something: expand terms specific to observability or Logfire, not the ones
  every developer uses daily.
- **Don't gloss the obvious** (see the don't-gloss list in §5). Spend the budget on the terms that
  actually block the reader.
- **Precise terms stay.** Introduce jargon; don't avoid it. The real word plus a hand-hold — never
  the hand-hold instead of the word.

### "Say where"
Any value the reader must fetch from elsewhere must say **where**. This is one of our most common
failures.

- "Copy your write token from **Project → Settings → Write tokens**."
- "Get an API key from the provider's dashboard (platform.openai.com/api-keys)."
- Every setup page states, before the first `configure()`, that a project + token are needed and
  where to get them.

### State consequences plainly
Whenever an action **sends data off the machine, costs money, drops/redacts data, or can't be
undone**, say so — plainly, at the point of decision, in a callout. State what changes, what data is
affected, and *when*. Never bury the critical warning below the configuration knobs.

### Code
- **Complete and runnable** — full imports, nothing elided the reader has to guess.
- **Highlight the change** — use highlight-lines or a diff so the one line that matters is obvious.
- **One idiom per page** — SDK task → tabbed runnable code; UI task → numbered steps with exact
  click targets. Don't interleave.
- **Show real output** — after a snippet that produces something, show what it produces.
- **Don't duplicate** — if Dev and Production differ by one line, show the base once and the delta.

### Screenshots and diagrams
- **Screenshots are proof, placed *after* the working step** — "you should now see this." Not
  decoration.
- **One teaching diagram** of a mental model beats five UI screenshots. Annotate and caption it.
- Ration them; keep them current. A stale screenshot is worse than none.

### Length
- Overview/concept page: **300–800 words.** A how-to is as long as one job needs and no longer. If a
  page is long because it covers several jobs, split it; if because of exhaustive option tables, move
  the tables to Reference and link them.

### Cross-linking
- Link the **first mention** of another feature to its home page.
- End pages with a short, reasoned fan-out ("Next steps: instrument a framework · run your first
  eval"), not a flat dump of every link.
- **One home per concept.** Link to it from elsewhere rather than copying it.

### Write technical English (for a global and machine audience)
Most readers are not native English speakers, and many "readers" are LLMs. Write **deliberate,
unambiguous English — closer to code than to conversational prose:**

- Short, direct sentences. One idea per sentence.
- Minimize idioms and regional dialect ("out of the box", "ballpark") — they don't translate and
  don't help a model.
- Use a **consistent word for a consistent thing.** If it's a "span", call it a "span" every time —
  don't alternate with "unit", "record", "item".
- Watch for structural ambiguity (dangling modifiers, unclear "it"/"this"). Re-read asking "could
  this parse two ways?"

### Ban the "README dialect"
Unedited AI output has tells. They are style violations here, whether a human or an agent wrote the
page:

- **Title Case Headings** — headings are sentence case and state a goal.
- **Passive voice by default** — "requests are recorded by the SDK" → "the SDK records every request".
- **Cliché openers and hype** — "In today's fast-paced world…", "unlock the power of…". Delete.
- **Hedging and throat-clearing** — "it's worth noting that", "generally speaking", "in order to".
- **Fabricated confidence** — never state a command, flag, or API method you haven't verified against
  the real product.

---

## 5. Words & terminology

**Reuse the glosses below verbatim** so the whole docs set reads as if it came from one mind.

### Product and feature naming
- The product is **Pydantic Logfire**, or **Logfire** in running prose (capitalized "Logfire", never
  "logfire" — that's the package/CLI in code).
- Use the **user-searchable** feature name, not the internal one (e.g. "Feature Flags", not the
  internal store name). Feature names are **Title Case**; don't invent new names for existing
  features mid-doc.

### Words and phrases to AVOID
- **Hype / marketing** (cut or replace with a concrete claim): `seamless(ly)`, `powerful`, `robust`,
  `blazing (fast)`, `effortless`, `magical`, `world-class`, `cutting-edge`, `next-generation`,
  `simply`, `just` (as in "just run"), `easy`/`easily`, `lightweight` (unless quantified).
- **Filler** (delete): "It's that simple!", "Cool, right?", "as the name suggests", "needless to
  say", "of course", "obviously", "as you can see", "basically", "in order to" (→ "to").
- **Vague verbs** (replace with a specific one): `leverage`/`utilize` → use; `enable you to` → let
  you; `facilitate` → help; `handle` → say what it does.
- **Our internals as reader words** (code/reference only): `span processor`, `exporter` (in setup
  copy), `ASGI middleware`, `OTLP endpoint` (without gloss), `proxy tracer provider`, `instrumentation
  package` (gloss it), `atomic unit of telemetry`.
- **Battlecard language:** don't name other products, and don't frame against "other tools" / "AI-only
  tools can't…" in feature docs. Any head-to-head belongs only on the dedicated comparisons page.
  Everywhere else, teach our advantage by *showing* it (the full-stack scenario), not by comparison.
- **Undefined jargon on first use** (define it — see glossary): `span`, `trace`, `instrument`, `OTLP`,
  `sampling`, `scrubbing`, `PII`, `SLO`, `eval`, `scorer`, `OFREP`, `collector`.

### Words to PREFER
- Plain verbs for the reader's action: **see, find, send, track, watch, redact, roll out, measure,
  query, alert.**
- Outcome nouns over mechanism nouns: **request, error, query, cost, latency, conversation, tool
  call** over `span`, `attribute`, `processor` when addressing a goal.
- "Send data to Logfire" over "export telemetry". "Add a few lines" over "instrument".
- Say the consequence in the reader's terms: "sent to and stored in Logfire", "counts toward your
  cost", "can't be undone".

### Don't-gloss list (the reader already knows these)
`AI`, `LLM`, `SDK`, `API`, `JSON`, `HTTP`, `URL`, `CLI`, `environment variable`, `package`, `import`, `function`,
`database`, `endpoint`, `request`. Spend the definition budget on the terms below instead.

### The canonical glossary
Use these exact hand-holds at a term's first use on a page. Keep the real term; add the gloss. If you
need a term that isn't here, add it here in the same one-clause style, then use it — the glossary is
append-only shared infrastructure.

**Observability core**
- **span** — one unit of work: a single operation, with a name, a start, and a duration.
- **trace** — the full journey of one request, made of nested spans.
- **log** — a timestamped record of a single event (no duration).
- **metric** — a number tracked over time, like requests per second or CPU load.
- **instrument** (verb) — add a few lines (or an integration) so Logfire can see what your code is doing.
- **OpenTelemetry (OTel)** — the open industry standard for collecting traces, metrics, and logs;
  anything OpenTelemetry-compatible works with Logfire.
- **OpenTelemetry Protocol (OTLP)** — the standard wire format Logfire uses to receive that data.
- **OpenTelemetry Collector** — a separate program that sits between your apps and Logfire, gathering
  telemetry and forwarding it.
- **distributed tracing** — stitching the spans from several services into one trace.
- **sampling** — keeping a representative subset of traces to control cost and volume (unkept traces
  are not sent).
- **baggage** — small key/value data that rides along with a request across services.
- **write token** — the credential your deployed app uses to send data to a Logfire project.
- **scrubbing / redact** — automatically finding and hiding sensitive values (passwords, tokens, PII)
  in your telemetry, on your machine, before anything is sent.
- **personally identifiable information (PII)** — data that identifies a person (email, name, IP…).

**Monitoring & reliability**
- **service level objective (SLO)** — a target for how reliable a service should be (e.g. 99.9% of
  requests succeed).
- **error budget** — how much unreliability an SLO still allows before you've broken it.
- **alert** — a query Logfire runs on a schedule; when it returns rows, Logfire notifies you.
- **issue** — a group of the same error occurring repeatedly, tracked over time.

**AI engineering**
- **evaluation (eval)** — a repeatable test of an AI system's output quality — like a test suite for
  software that has no single right answer.
- **offline eval** — running evals against a fixed dataset, like a test suite.
- **online / live eval** — scoring real production traffic as it happens, like monitoring.
- **scorer / evaluator** — the thing that judges an output and produces a score (code, or an LLM).
- **score** — one saved quality rating for an output, from a human or an automated scorer.
- **LLM-as-a-judge** — using a language model to score another model's output.
- **dataset** — a collection of test cases (inputs and expected outputs) you evaluate against.
- **experiment** — one run of your AI over a dataset, producing scores you can compare across versions.
- **session** — a group of related interactions (e.g. one multi-turn conversation).
- **token** (LLM) — the unit models read and bill by; a few characters of text. *(Disambiguate from
  "write token" when both appear.)*
- **prompt management** — versioning prompts outside your code so you can change and roll them back
  without a redeploy.
- **AI Gateway** — one endpoint in front of every model provider that routes calls, controls spend,
  and adds guardrails.
- **guardrails** — policies that check or redact model inputs/outputs (e.g. block PII).

**Product & platform**
- **feature flag** — a switch that turns a feature on for some users without redeploying.
- **OpenFeature Remote Evaluation Protocol (OFREP)** — an open standard for evaluating feature flags
  from any client.
- **A/B test / experiment** — showing variants to different users and comparing a metric.
- **role-based access control (RBAC)** — controlling who can do what, by role.
- **data region / residency** — which geographic location your data is stored in.

### Spelling and mechanics
- US English. Oxford comma.
- Sentence case for headings ("Find your slowest endpoints"); Title Case only for proper feature names.
- Code, commands, file paths, env vars, and identifiers in `monospace`.
- Numbers: spell out one–nine in prose; numerals for 10+ and anything with a unit ("5 minutes",
  "3 spans").

The banned words, required-gloss terms, and naming rules are meant to be **machine-enforced** (see
§7) — generated into linter rules and run in CI, so terminology drift is caught before review rather
than argued about in it.

---

## 6. Pre-publish checklist

Every page must pass this before it merges. Skip a line only if it doesn't apply to the page type.

**Orientation**
- [ ] The first sentence states the reader's **outcome**, not our mechanism or a bare feature name.
- [ ] The page says **what it's for** (and, where relevant, when *not* to use it) before any config.
- [ ] The title and headings are **user goals**, not internal nouns.

**Clarity**
- [ ] Every **term of art is defined in place at first use** (glossary wording).
- [ ] Every **acronym is spelled out** the first time on the page.
- [ ] No banned hype/filler words; no internal terms in reader copy.

**Actionability**
- [ ] Every value the reader must fetch **says where** to get it (token, key, setting).
- [ ] The **common path comes first**; manual/rare/dangerous paths are demoted and labeled.
- [ ] Code is **complete and runnable**, with the change highlighted; no duplicated blocks.
- [ ] There's a **"you should now see X"** verify step, with a screenshot if the result is visual.
- [ ] There's a **Troubleshooting** section (setup / integration / how-to pages).

**Honesty & safety**
- [ ] Any action that **sends data off the machine, costs money, drops/redacts data, or is
      irreversible** has a plain consequence callout, at the decision point.
- [ ] Maturity is marked with the correct badge; GA is unbadged; no stacked labels.
- [ ] No other product is named outside the dedicated comparisons page.

**Craft**
- [ ] Overview/concept pages are **300–800 words**; the page doesn't mix an overview with a full how-to.
- [ ] The page **ends deliberately** (verify / next steps / troubleshooting) — it doesn't trail off.
- [ ] First mentions of other features **link** to their home page; there's a short reasoned fan-out.
- [ ] Frontmatter `title` + `description` follow the one convention.

### Do / Don't quick reference

| Do | Don't |
|----|-------|
| Open with the reader's outcome | Open with mechanism, a feature name, badges, or backstory |
| One page per user job | One page per feature, surface, or object |
| Define "span", "eval", "OTLP" on first use | Assume the reader knows them; or gloss "SDK"/"API" |
| Say where the token comes from | Call `configure()` as if it just works |
| State consequences at the decision point | Bury the warning below the config knobs |
| Lead with the 95% path | Lead with "how to disable it" or the manual path |
| Show the real output/screenshot | End at `report.print()` with no output shown |
| Add Verify + Troubleshooting | Assume it worked |
| Teach the practice, then the API | Dump the API and hope they infer the concept |
| Keep overviews short and fan out | Grow an overview into a 280-line manual |
| Say when *not* to use a feature | Pretend every reader needs it |

### Anti-patterns and their fixes

1. **Name-as-description.** "The live view is the focal point of Logfire (as the name suggests)." →
   State what it's *for*: "Watch traces arrive as they happen — tail a request while you reproduce a
   bug, or watch errors during a deploy."
2. **Mechanism-first opening.** "Logfire creates a span for every query executed by a SQLAlchemy
   engine." → "See every database query your app runs — the SQL, how long it took, and which failed."
3. **Jargon cold.** A page opening with "context propagation, sampling, spans" and no glosses. →
   Define each on first use; lead with the goal.
4. **Missing "where".** `logfire.configure()` with no mention of the project/token or where to get it.
   → Add the prerequisite line with the exact location.
5. **Buried consequence.** "Disabling scrubbing" as the first section with no warning it then sends
   raw PII. → Demote it; add the plain warning at the decision point.
6. **Rare-path-first.** A distributed-tracing page leading with manual context propagation it admits
   you "shouldn't usually need." → Lead with the automatic integration path.
7. **Invisible payoff.** An eval example that calls `report.print()` but never shows the output. →
   Show the printed table with real numbers.
8. **Battlecard in the docs.** A "comparison to other tools" section inside a feature page. → Move it
   to the comparisons page; teach the advantage by showing the full-stack scenario.
9. **Page that trails off.** A concept page stopping mid-sentence. → Finish every section; end with a
   fan-out.
10. **One-doc-per-surface sprawl.** Separate pages for each internal object. → One page per user job;
    the surfaces are sections.
11. **Duplicated snippets.** Dev and Production tabs pasting the same block. → Show the base once,
    then only the delta.
12. **Filler and hype.** "It is simple as that! Cool, right?"; "powerful, seamless observability." →
    Delete, or replace with a concrete checkpoint sentence.

### Reviewer rubric
When reviewing a docs PR, grade five qualities and block on any red:
**Findability · Orientation · Approachability · Actionability · Honesty.** A page that is accurate but
fails Orientation or Approachability is **not done** — "technically all here" is not the bar.

---

## 7. AI-assisted authoring

Much of this documentation is drafted with AI agents, and much of it is *read* by them (Logfire's own
MCP server and coding-agent skills consume docs). These rules keep that safe.

### Two audiences: precise for machines, mental model for humans
- **Machines** (LLMs, agents, our MCP server) want **precise, reliably extractable** reference and
  procedures: exact commands, exact names, stable structure, semantic metadata.
- **Humans** want a **mental model** — the *why*, the *when*, and where to stop.

Map this to page types: **Reference and How-to must be machine-precise**; **Overviews and Concepts
must build the mental model.** A reference page that reads like an essay fails the machine; a concept
page that's just an API dump fails the human.

### Write well for humans; package for machines
**Do not write differently for LLMs.** Well-structured prose that's good for a human is already good
for a model. Don't mangle tables, diagrams, or narrative to "please" a retrieval system. The
difference is **packaging, not composition**: consistent frontmatter/metadata on every page, an
`llms.txt` index (and per-page `.md` availability) so agents consume docs the same way humans do, and
one canonical home per concept.

### Rules for AI-drafted docs
1. **Same review bar as human work.** An AI-drafted page passes the exact pre-publish checklist and
   reviewer rubric like any other; existing ≠ done.
2. **Validate every command, snippet, and API against the real product before publishing.** LLMs
   hallucinate plausible-but-wrong commands, flags, and method names. Every code sample must have been
   run or checked against the current SDK/UI. **Non-negotiable.**
3. **Humans own information architecture.** Where a page goes, how the nav is shaped, what to cut —
   human decisions. Agents fill templates and draft prose; they don't decide structure.
4. **Ground in product truth, not the spec.** Match the real UI, real error messages, and real edge
   cases — found by using the product, not reading the design doc.
5. **Lightweight disclosure.** When a page is substantially AI-drafted, note it in the PR (which
   model, how much human editing) so reviewers calibrate scrutiny.
6. **Ban the "README dialect"** (see §4).

### Automation: deterministic tools first, LLM to filter
Docs are code; gate them like code, in this order — **deterministic checks first, then let an LLM
filter, never find.** Deterministic tools detect issues far more reliably and cheaply than a model;
the LLM's job is to prioritize and explain what the tools already found. Target pipeline (build toward
it, not all required day one):

1. **Prose linter** enforcing this guide's terminology and banned words.
2. **Link checker** — no dead links.
3. **Spell/typo check.**
4. **Build + snippet execution** — the docs build passes and runnable snippets run.
5. **Only then, an LLM review pass** — non-blocking inline suggestions on the human-judgment issues
   linters can't catch (does it open with the outcome? is the term defined? is the consequence stated?).

### Persona testing
Before a high-traffic page ships, feed it to an agent role-playing the target reader — above all the
**cross-field newcomer** from §1 — and ask: where did you get lost, what term stopped you, what
couldn't you find? Cheap UX research that finds gaps before real users do.

### The one rule that overrides "ship and iterate"
Ship minimum viable documentation and improve from feedback — but **incompleteness is fine,
inaccuracy is not.** Never publish a command, flag, or method you haven't verified against the current
product.
