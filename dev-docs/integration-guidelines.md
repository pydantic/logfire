# Integration guidelines

## Using this checklist

- Required: use this checklist when creating, changing, reviewing, or auditing a Logfire integration, including integrations without an `instrument_*` method.
- Required: read each category and decide which items apply. “Conditional” means required when the stated condition applies; “nice to have” means an improvement rather than a merge requirement.
- Required: support conclusions with implementation, upstream source, documentation, or test evidence. A checked box or an existing integration doing the same thing is not sufficient evidence.
- Required: distinguish confirmed defects, missing evidence, intentional limitations, and optional improvements. Explain material exceptions and unsupported cases.
- Required: assess the changed behavior and relevant interactions; an unrelated pre-existing gap need not block a focused fix. Record larger follow-up work separately.
- Required: check current repository conventions and upstream APIs rather than assuming examples or review comments are correct.

## Making the checklist available to agents and reviewers

- Required for the eventual checked-in version: keep one authoritative checklist, either within the skill or in a document linked by it, so implementation and review guidance stay aligned.
- Required for the eventual checked-in version: add guidance in the repository's `AGENTS.md` directing implementation agents and reviewers to consult the checklist for relevant changes, including Cubic, Devin, and CodeRabbit.
- Conditional: where a review bot requires its own configuration or instruction file, point it to the same checklist using that bot's supported mechanism. An `AGENTS.md` instruction alone is not proof the bot reads it.
- Required: make the checklist usable as ordinary Markdown by reviewers that cannot invoke a skill.
- Required: make the skill's scope clear: developing and reviewing Logfire's integrations, rather than adding Logfire instrumentation to a user's application.
- Nice to have: retain concrete examples and lessons from reviews as supporting references without duplicating the checklist.

## Public API and typing

- Conditional: add or update the method on `Logfire` in `logfire-sdk/logfire/_internal/main.py` when Logfire owns a public instrumentation entry point.
  - External types for this method should be imported under `if TYPE_CHECKING` to avoid runtime dependencies on optional libraries.
- Conditional: expose new public methods through the module-level aliases and `__all__` in `logfire-sdk/logfire/__init__.py`.
- Conditional: update the `logfire-api` no-op implementation and forwarding aliases, preserving behavior both with and without the real SDK installed. Do not hand-edit generated `.pyi` stubs.
- Required: use consistent names, defaults, parameter types, return types, and docstrings; describe side effects and the meaning of returned wrappers or handles.
- Required: preserve established public behavior unless a deliberate compatibility change is justified and documented.
- Conditional: expose useful upstream options and hooks through explicit parameters or passthrough arguments. Verify their actual signatures and availability in supported upstream versions.
  - Use `_UNSET` as the default argument value for arguments that are simply passed through to upstream instrumentors. Don't pass through unset values so that upstream instrumentors can use their own defaults. Document the last known default values in the docstring, but don't hardcode them in the signature. Document the caveat that upstream defaults may change. Don't use `_Unset` in the type hint, `_UNSET` is already typed as Any.
  - For OTel contrib instrumentors, inspect their source code to determine the parameters they accept and their types, then use those on the Logfire wrapper.
  - Tracer/logger/meter providers are an exception, they should be obtained from a Logfire instance rather than exposed in the public API.
  - Add `**kwargs: Any` to also pass through any future upstream parameters. Allow these to override the tracer/meter/logger provider parameters just in case an advanced user needs this, but don't document or test it, e.g. `upstream_instrumentor(**{'tracer_provider': logfire_instance.config.get_tracer_provider(), **kwargs})`.
- Required: keep optional-library imports lazy so importing Logfire does not require every integration dependency.
- Required: keep typing rigorous, including tests. Contain unavoidable dynamic patching or untyped upstream boundaries rather than spreading `Any` or blanket suppressions.
- Conditional: if possible without footguns, a `logfire.instrument_*` method should work with zero arguments and instrument globally.
- Nice to have: if the instrumented library has objects that can be instrumented individually, such as sessions, connections, or clients, the first positional argument of `logfire.instrument_*` should be a (typically optional) object to instrument in isolation.
- Required: instrumenting globally after users import classes or construct objects should still instrument those classes and objects where possible.
  - For example, prefer patching `__init__` directly on the original class rather than replacing the class in the module with a subclass that overrides `__init__`, so that users who already imported the class before instrumenting still get the instrumentation on instances they create afterwards. If this isn't possible, global instrumentation shouldn't be offered, and the method should require an object to instrument.
    - If global instrumentation is otherwise possible except with this ordering caveat, then `logfire run` should still automatically instrument globally, as it can do this before users import the library. The `Logfire` method should require an object to instrument, but `logfire run` can bypass this and use an internal API. See the flask integration for an example of this.
  - Similarly, rather patch the specific methods than the constructor, so that instrumenting after users have already created objects still instruments those objects. If that's not possible, document the limitation with a prominent warning.
- Conditional: if possible, instrumentation should happen in place, the instrumenting method shouldn't need to return a wrapped object. If this isn't possible, emphasize in documentation that the user must use the returned object instead of the original one.
- Conditional: parameters that are callbacks/hooks that the user must define, whose signature we control (as opposed to being passed through to upstream), should be callables that accept a single argument of a contrainer type we define. That way the type can grow in the future to include more attributes instead of adding parameters to the callback signature and breaking existing callbacks. Do this even if the container type only has one field. The container type should be exposed publicly in the `logfire.integrations.<integration>` module so that users can import it and use it in their type hints to define their callback.
- Required: call `_warn_if_not_initialized_for_instrumentation` in every `logfire.instrument_*`.

## Dependencies and installation

- Required: declare packages needed by tests and type checking in the root development dependencies, with appropriate Python and platform markers, and update `uv.lock` when dependencies change.
- Conditional: add or update an install extra in `logfire-sdk/pyproject.toml` when users need an additional instrumentation package. Do not require an extra merely because another integration has one; integrations relying only on the user's existing library may not need one.
- Conditional: when extra dependencies are needed to use the integration, make missing-dependency and unsupported-version errors actionable, with the correct distribution name and install command. The error message should suggest installing the extra if one exists. For example, `logfire.instrument_fastapi()` suggests `pip install logfire[fastapi]` if the `opentelemetry-instrumentation-fastapi` package is not installed. It doesn't need to check if `fastapi` itself is installed or make suggestions about that, the user is assumed to have already installed the library they are trying to instrument.
- Required: avoid disguising an upstream package's internal or transitive import failure as a missing optional dependency.
- Conditional: account for package-name/import-name differences, binary alternatives, and upstream version ranges that cannot coexist with supported Logfire dependencies.

## Logfire configuration and OpenTelemetry interoperability

- Required: route telemetry through the intended Logfire configuration rather than silently using unrelated global providers or the first instance encountered.
- Conditional: pass Logfire's tracer, meter, or logger providers/components to upstream instrumentation for the signals it emits. Do not invent metrics or logs just to populate every signal type.
- Required: ensure the instrumentation scope name identifies the library being instrumented. For custom integrations, use `logfire_instance.with_settings(custom_scope_suffix='<library name>')`.
- Required: consider coexistence with upstream auto-instrumentation, manually installed OpenTelemetry instrumentation, and related Logfire _integrations_; avoid duplicate wrapping or exporting.
- Required: avoid silently replacing application-owned providers or configuring unrelated global OpenTelemetry state.
- Conditional: verify behavior before and after `logfire.configure()`, reconfiguration, or shutdown where the integration captures providers or components that may outlive a configuration.

## Installation lifecycle and state

- Required: define repeated-call behavior, including whether changed settings are ignored, warned about, or applied. Do not accidentally stack wrappers or register callbacks repeatedly.
- Conditional: test both installation orders when global instrumentation and per-object instrumentation can coexist; make configuration precedence clear.
- Conditional: keep separate objects' Logfire instances and capture settings independent when per-object configuration is supported.
- Required: do not record unrelated, uninstrumented objects when only a particular object was selected.
- Conditional: handle concurrent installation or mutable shared state safely when concurrent calls are supported or reasonably expected.
- Conditional: avoid retaining clients, connections, or callbacks indefinitely through instrumentation bookkeeping; consider weak references and callback cleanup where appropriate.
- Conditional: if uninstrumentation is offered, restore behavior without removing someone else's instrumentation and define whether later installation works. A new public uninstrument API is not universally required.
- Conditional: consider process forks, worker startup, and reloaders for integrations used in those environments; document necessary installation order.

## Preserving application behavior

- Required: preserve arguments, return values, object identity where significant, exceptions, and library side effects.
- Required: keep instrumentation failures from breaking otherwise successful application work, using the repository's internal-error handling conventions where appropriate. Do not swallow application exceptions.
- Required: preserve function metadata and binding behavior where wrapping affects them.
- Conditional: preserve positional arguments, keyword arguments, custom subclasses, inherited methods, and calls through `super()` for APIs that allow them.
- Conditional: do not eagerly consume iterators, streams, generators, or lazy response bodies, issue hidden requests, or parse twice merely to obtain telemetry.
- Conditional: preserve async cancellation, context-manager behavior, cleanup, and resource ownership.
- Conditional: handle early exit, explicit close, failed iteration or parsing, and repeated close/parse calls for deferred operations; define what happens if the caller abandons them.
- Required: avoid recursive instrumentation of telemetry export or other instrumentation internals.

## Spans, context, and errors

- Required: check OpenTelemetry semantic conventions; justify custom attributes and account for convention-version differences.
- Required: give spans meaningful names and boundaries representing the operation the user is trying to observe; avoid unbounded values such as full URLs or SQL text in span names.
- Required: keep span names low cardinality. Span names should directly include small, nonsensitive, low cardinality values rather than only formatting them in the message, so that other OTel backends which don't support logfire messages can still display a readable span name instead of a template. Use the `_span_name` argument of `Logfire.span` where appropriate. Don't pass f-strings directly to the logfire span/log methods, e.g. don't do `logfire.span(f'foo {bar}')`, as this requires f-string magic which the user may have disabled. Instead, write `logfire_instance.span('foo', _span_name=f'foo {bar}', bar=bar)`.
- Required: for attributes that are worth including in the message for convenient readability, but may be long, sensitive, or of high cardinality, put their names in the message template but not the span name, so that message formatting can handle truncation and scrubbing. For example, `logfire_instance.span('foo {bar}', _span_name='foo', bar=bar)`, where `bar` is a possibly long or sensitive value.
- Check span names and messages in tests and assure they're appropriate.
- Required: avoid changing span or attribute names in existing integrations to prevent breaking dashboards and alert queries, unless a deliberate compatibility change is justified and documented.
- Required: preserve the caller's trace context, produce the intended parent-child relationships, and restore context after success and failure.
- Conditional: propagate context through tasks, threads, callbacks, queues, and process or network boundaries where the integration promises it. Use links where parent-child relationships would be misleading.
- Conditional: ensure lazy and streaming operations do not leave their spans current during unrelated application work or detach context in a different task from the one that attached it.
- Required: record application errors with appropriate exception details and status, without classifying normal control flow or cancellation as failures indiscriminately.
- Conditional: consider handled errors, retries, and failures during stream consumption or resource cleanup, rather than only errors at the initial call.
- Required: use appropriate span kinds.
- Required: check message formatting, timestamps, durations, events, and attributes in the actual exported telemetry, including behavior when spans are not recording.

## Captured data and privacy

- Required: state what is captured by default and what requires opt-in, especially request/response bodies, database parameters, prompts, generated code, function arguments, and results.
- Required: For attributes that should be scrubbed when appropriate, don't use an attribute name that's marked as safe by the scrubber. Test representative secrets rather than assuming a field is scrubbed. For example, SQL queries shouldn't be scrubbed, even though they may contain secrets, because innocent queries containing sensitive-looking table/column names would be a false positive. But an object containing structured query parameters should be scrubbed because values can be separated, so it shouldn't use a safe name like `db.statement`.
- Required: avoid exporting credentials, authorization headers, URL user information, or other known secrets in connection metadata or identifiers.
- Required: handle absent, malformed, or unserializable metadata without breaking application behavior.
- Conditional: make custom capture settings, header allowlists, exclusions, and hooks work consistently across relevant API variants.
- Nice to have: provide useful capture controls when default upstream capture is too broad; this does not require every integration to expose the same options.

## Metrics and logs

- Conditional: when metrics are emitted, verify names, units, instrument types, labels, aggregation, and collection behavior against upstream conventions and Logfire configuration.
- Conditional: keep metric labels bounded; avoid arbitrary SQL, URLs, prompts, function names, or exception messages creating unbounded time series.
- Conditional: verify metric callbacks and instruments are not registered repeatedly, leaked, or lost when associated objects are created and destroyed.
- Conditional: check relevant sampling and trace-context behavior for metrics; do not assume span sampling should suppress measurements.
- Conditional: when logs are emitted, preserve severity, timestamps, structured attributes, messages, and trace correlation, and avoid duplicate forwarding.

## Command-line discovery and recommendations

- Conditional: update `logfire run` package detection, target aliases, extra mappings, minimum-version checks, or call arguments when the integration can be usefully enabled or recommended there.
- Required when changing CLI discovery: distinguish the library being instrumented from the package providing instrumentation, including nonmatching distribution/import names.
- Required when changing CLI discovery: ensure generated install suggestions and instrumentation calls work, respect exclusions, and avoid duplicates with overlapping integrations.
- Conditional: explain why automatic enablement is inappropriate when setup needs an application/client object, explicit capture choices, or other information unavailable to the CLI.

## Tests and compatibility evidence

- Required: exercise user-facing APIs and inspect exported telemetry with `TestExporter` and the relevant metric/log readers. Follow repository snapshot conventions and review generated snapshots for correctness. At least one test should contain a `snapshot` of all exported spans in full. Not a subset of spans, and not just part of the span dicts. Use targeted dirty-equals matchers for non-deterministic fields such as timestamps, IDs, and random values.
- Required: exercise the real library behavior as far as practical. Use fakes or mocks at external boundaries, and check that they do not hide signature, binding, lazy-consumption, or subclass behavior.
- Conditional: use local services, in-process transports, or VCR cassettes for external interactions as appropriate. Do not require live credentials or paid services for ordinary CI; keep secrets out of recordings.
- Conditional: prefer VCR cassettes over mocked HTTP sessions/transports.
- Required: cover successful operations, errors, configuration choices, missing dependencies, and applicable lifecycle cases; prove important negative behavior such as no duplicate spans or no parameter capture by default.
- Required: restore patched functions, global providers, installation flags, callbacks, and other modified state, including state introduced by `test_logfire_api.py`. Tests should work alone and alongside related integration tests without depending on execution order.
- Conditional: test real parent context and context restoration across concurrency or deferred execution where those paths are supported.
- Conditional: add focused compatibility coverage or version-specific handling when using APIs that changed across the supported range; avoid broad skips hiding regressions.

## Documentation and discoverability

- Required: follow `dev-docs/documentation-style-guide.md` for public documentation, including plain-language explanations of unfamiliar terms.
- Conditional: add or update the integration page, integrations index, and `docs/navigation.yml` when introducing or changing a public integration. An existing general page may suffice when it accurately covers the feature.
- Use `{{ install_logfire(extras=['...']) }}` in the docs when an extra is required for the integration, and `{{ install_logfire() }}` when no extra is required. Do not hardcode `pip install logfire[extra]` in the docs.
- Required: explain what users will capture, prerequisites, installation, configuration order, and a complete runnable example with the instrumentation change easy to spot.
- Required: describe supported versions, capture defaults, significant limitations, process-wide effects, and repeated-call behavior where these affect user decisions.
- Required: provide a concrete verification step with expected telemetry and troubleshooting for likely failures.
- Required: provide a minimal, complete, runnable python code example that users can copy and run to verify the integration works.
  - This should be a 'hello world' intended to demonstrate the integration, not the library.
  - Aim for one file, or as few as possible.
  - If other processes are needed, like a database, try providing a simple docker command.
  - Use `hl_lines` to highlight the instrumentation method calls, particularly `logfire.configure()` and `logfire.instrument_*()`.
- Required: keep install commands, method signatures, examples, API-reference links, and actual behavior consistent.
- Required: use source-relative `.md` links without a deployment-specific `/docs` prefix; verify affected pages and anchors in a rendered preview using the unified-docs workflow, not MkDocs.
- Nice to have: include a representative trace, screenshot, or worked output where it helps users recognize success.
- Conditional: link to upstream documentation, especially for required dependencies such as the OTel contrib library.

## Overhead and maintainability

- Required: avoid obvious per-operation waste, blocking work in async paths, unbounded buffering, or retaining large payloads unnecessarily.
- Conditional: measure overhead when wrapping very frequent or cheap operations, adding expensive capture, or claiming a performance improvement; benchmarks are not mandatory for every thin wrapper.
- Required: keep custom logic focused on behavior Logfire needs; avoid copying upstream instrumentation or generalizing a helper without a concrete benefit.
- Required: separate upstream defects from Logfire defects and record significant upstream dependencies or workarounds so future changes can be reviewed intelligently.
- Nice to have: move broadly useful fixes upstream and track removal of temporary compatibility workarounds.
