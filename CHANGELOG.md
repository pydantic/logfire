# Release Notes

## [v2.4.1] (2024-11-21)

* Allow new context argument of metric instrument methods to be passed positionally by @alexmojaki in [#616](https://github.com/pydantic/logfire/pull/616)

## [v2.4.0] (2024-11-20)

* Support `logfire.instrument` without arguments by @Kludex in [#607](https://github.com/pydantic/logfire/pull/607)
* Handle internal errors in `create_json_schema` by @alexmojaki in [#613](https://github.com/pydantic/logfire/pull/613)
* Handle errors in auto-tracing better by @alexmojaki in [#610](https://github.com/pydantic/logfire/pull/610)

## [v2.3.0] (2024-11-14)

* Respect repr on fields when logging a dataclass by @dmontagu in [#592](https://github.com/pydantic/logfire/pull/592)
* Allow `extract_args` to be an iterable of argument names by @alexmojaki in [#570](https://github.com/pydantic/logfire/pull/570)
* Make metric instrument methods compatible with older OTel versions by @alexmojaki in [#600](https://github.com/pydantic/logfire/pull/600)
* Add span links by @Kludex in [#587](https://github.com/pydantic/logfire/pull/587)

## [v2.2.1] (2024-11-13)

* Ignore trivial/empty functions in auto-tracing by @alexmojaki in [#596](https://github.com/pydantic/logfire/pull/596)
* Handle missing attributes in `_custom_object_schema` by @alexmojaki in [#597](https://github.com/pydantic/logfire/pull/597)
* Let user know what they should install for integrations by @Kludex in [#593](https://github.com/pydantic/logfire/pull/593)

## [v2.2.0] (2024-11-13)

* Allow instrumenting a single httpx client by @alexmojaki in [#575](https://github.com/pydantic/logfire/pull/575)
* Log LLM tool call for streamed response by @jackmpcollins in [#545](https://github.com/pydantic/logfire/pull/545)

## [v2.1.2] (2024-11-04)

* Check `.logfire` for creds to respect `'if-token-present'` setting by @sydney-runkle in [#561](https://github.com/pydantic/logfire/pull/561)

## [v2.1.1] (2024-10-31)

* Use `functools.wraps` in `@logfire.instrument` by @alexmojaki in [#562](https://github.com/pydantic/logfire/pull/562)
* Set `logfire.code.work_dir` resource attribute whenever other code source attributes are present by @alexmojaki in [#563](https://github.com/pydantic/logfire/pull/563)
* Don't scrub `logfire.logger_name` by @alexmojaki in [#564](https://github.com/pydantic/logfire/pull/564)

## [v2.1.0] (2024-10-30)

* Add ASGI & WSGI instrument methods by @Kludex in [#324](https://github.com/pydantic/logfire/pull/324)
* Add `logfire.work_dir` resource attribute by @Kludex in [#532](https://github.com/pydantic/logfire/pull/532)
* Add `logfire.configure(environment=...)` by @Kludex in [#557](https://github.com/pydantic/logfire/pull/557)
* Show message from API backend when checking token fails by @alexmojaki in [#559](https://github.com/pydantic/logfire/pull/559)

## [v2.0.0] (2024-10-30)

* `@logfire.instrument()` no longer needs source code by @alexmojaki in [#543](https://github.com/pydantic/logfire/pull/543). **BREAKING CHANGES** caused by this:
  * Functions decorated with `@logfire.instrument()` and functions nested within them can now be auto-traced unlike before. Use `@logfire.no_auto_trace` anywhere on functions you want to exclude, especially the instrumented function.
  * Decorated async generator functions won't support the `.asend` method properly - the generator will only receive `None`. But `instrument` shouldn't be used on generators anyway unless the generator is being used as a context manager, so new warnings about this have been added. See https://logfire.pydantic.dev/docs/guides/advanced/generators/#using-logfireinstrument

## [v1.3.2] (2024-10-29)

* Handle NonRecordingSpans for fastapi arguments by @alexmojaki in [#551](https://github.com/pydantic/logfire/pull/551)
* Preserve docstrings in auto-tracing by @alexmojaki in [#550](https://github.com/pydantic/logfire/pull/550)

## [v1.3.1] (2024-10-28)

* Handle null fastapi route.name and route.operation_id by @alexmojaki in [#547](https://github.com/pydantic/logfire/pull/547)

## [v1.3.0] (2024-10-24)

* Add Code Source links by @Kludex in [#451](https://github.com/pydantic/logfire/pull/451) and [#505](https://github.com/pydantic/logfire/pull/505)
* Add fastapi arguments attributes directly on the root OTel span, remove `use_opentelemetry_instrumentation` kwarg by @alexmojaki in [#509](https://github.com/pydantic/logfire/pull/509)
* Allow setting tags on logfire spans by @AdolfoVillalobos in [#497](https://github.com/pydantic/logfire/pull/497)
* Add logger name to `LogfireLoggingHandler` spans by @samuelcolvin in [#534](https://github.com/pydantic/logfire/pull/534)
* Format `None` as `None` instead of `null` in messages by @alexmojaki in [#525](https://github.com/pydantic/logfire/pull/525)
* Use `PYTEST_VERSION` instead of `PYTEST_CURRENT_TEST` to detect `logfire.configure()` being called within a pytest run but outside any test by @Kludex in [#531](https://github.com/pydantic/logfire/pull/531)

## [v1.2.0] (2024-10-17)

* Add `local` parameter to `logfire.configure()` by @alexmojaki in [#508](https://github.com/pydantic/logfire/pull/508)

## [v1.1.0] (2024-10-14)

* Fix error in checking for generators in auto-tracing by @alexmojaki in https://github.com/pydantic/logfire/pull/498
* Support `'if-token-present'` for env var `'LOGFIRE_SEND_TO_LOGFIRE'` by @sydney-runkle in https://github.com/pydantic/logfire/pull/488
* Use `Compression.Gzip` by @Kludex in https://github.com/pydantic/logfire/pull/491

## [v1.0.1] (2024-10-02)

* Fix warning about unregistered MetricReaders by @alexmojaki in https://github.com/pydantic/logfire/pull/465

## [v1.0.0] (2024-09-30)

* Upgrade `DeprecationWarning`s to `UserWarning`s by @alexmojaki in https://github.com/pydantic/logfire/pull/458
* Update query client APIs by @dmontagu in https://github.com/pydantic/logfire/pull/454

## [v0.55.0] (2024-09-27)

* Replace `pydantic_plugin` in `logfire.configure()` with `logfire.instrument_pydantic()` by @alexmojaki in https://github.com/pydantic/logfire/pull/453
* Keep `METRICS_PREFERRED_TEMPORALITY` private by @alexmojaki in https://github.com/pydantic/logfire/pull/456
* Use `SeededRandomIdGenerator` by default to prevent interference from `random.seed` by @alexmojaki in https://github.com/pydantic/logfire/pull/457

## [v0.54.0] (2024-09-26)

* **Changes in `logfire.configure()`:**
  * Remove `show_summary` and `fast_shutdown` by @alexmojaki in https://github.com/pydantic/logfire/pull/431
  * Move `base_url`, `id_generator`, and `ns_timestamp_generator` parameters into `advanced: AdvancedOptions` by @alexmojaki in https://github.com/pydantic/logfire/pull/432
  * Add `metrics` parameter by @alexmojaki in https://github.com/pydantic/logfire/pull/444
* Remove default `min_duration` for `install_auto_tracing` by @alexmojaki in https://github.com/pydantic/logfire/pull/446

## [v0.53.0] (2024-09-17)

* Tail sampling by @alexmojaki in https://github.com/pydantic/logfire/pull/407
* Use OTEL scopes better, especially instead of tags by @alexmojaki in https://github.com/pydantic/logfire/pull/420
* Deprecate `project_name` in `logfire.configure()`, remove old kwargs from signature  by @alexmojaki in https://github.com/pydantic/logfire/pull/428
* Fix websocket span messages by @alexmojaki in https://github.com/pydantic/logfire/pull/426
* Remove warning about attribute/variable name conflicts in f-string magic by @alexmojaki in https://github.com/pydantic/logfire/pull/418

## [v0.52.0] (2024-09-05)

* Handle FastAPI update with SolvedDependencies by @alexmojaki in https://github.com/pydantic/logfire/pull/415
* Add experimental client for the Logfire Query API by @dmontagu in https://github.com/pydantic/logfire/pull/405
* Remove `default_span_processor` parameter from `configure` by @alexmojaki in https://github.com/pydantic/logfire/pull/400
* Remove `custom_scope_suffix` parameter of `Logfire.log` by @alexmojaki in https://github.com/pydantic/logfire/pull/399
* Add missing `service_version` field to `_LogfireConfigData` so that it gets copied into subprocesses by @alexmojaki in https://github.com/pydantic/logfire/pull/401

## [v0.51.0] (2024-08-22)

### BREAKING CHANGES

* **System metrics are no longer collected by default** when the correct dependency is installed. Use [`logfire.instrument_system_metrics()`](https://logfire.pydantic.dev/docs/integrations/system-metrics/) to enable system metrics collection. **If you are simply using the old 'Basic System Metrics' dashboard, then no further code changes are required, but that dashboard will no longer work properly and you should create a new dashboard from the template named 'Basic System Metrics (Logfire)'**. If you were using other collected metrics, see the documentation for how to collect those. By @alexmojaki in https://github.com/pydantic/logfire/pull/373
* Stop collecting package versions by @alexmojaki in https://github.com/pydantic/logfire/pull/387
* Don't auto-trace generators by @alexmojaki in https://github.com/pydantic/logfire/pull/386
* Disable ASGI send/receive spans by default by @alexmojaki in https://github.com/pydantic/logfire/pull/371

### Other fixes

* Add py.typed file to logfire-api by @jackmpcollins in https://github.com/pydantic/logfire/pull/379
* Check `LambdaRuntimeClient` before logging tracebacks in `_ensure_flush_after_aws_lambda` by @alexmojaki in https://github.com/pydantic/logfire/pull/388

## [v0.50.1] (2024-08-06)

(Previously released as `v0.50.0`, then yanked due to https://github.com/pydantic/logfire/issues/367)

* **BREAKING CHANGES:** Separate sending to Logfire from using standard OTEL environment variables by @alexmojaki in https://github.com/pydantic/logfire/pull/351. See https://logfire.pydantic.dev/docs/guides/advanced/alternative_backends/ for details. Highlights:
  * `OTEL_EXPORTER_OTLP_ENDPOINT` is no longer just an alternative to `LOGFIRE_BASE_URL`. Setting `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, and/or `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` will set up appropriate exporters *in addition* to sending to Logfire, which must be turned off separately if desired. These are basic exporters relying on OTEL defaults. In particular they don't use our custom retrying logic.
  * `LOGFIRE_BASE_URL` / `logfire.configure(base_url=...)` is now only intended for actual alternative Logfire backends, which are currently only available to Logfire developers, and unlike `OTEL_EXPORTER_OTLP_ENDPOINT` requires authenticating with Logfire.
  * Pending spans are only sent to logfire-specific exporters.
* Add `capture_statement` to Redis instrumentation by @Kludex in https://github.com/pydantic/logfire/pull/355

## [v0.49.1] (2024-08-05)

* Add missing return on instrument methods by @Kludex in https://github.com/pydantic/logfire/pull/360
* Add `logfire.exception()` to `logfire-api` by @Kludex in https://github.com/pydantic/logfire/pull/358
* Remove `TypeAlias` from code source by @Kludex in https://github.com/pydantic/logfire/pull/359
* Turn `ParamSpec` non-private by @Kludex in https://github.com/pydantic/logfire/pull/361

## [v0.49.0] (2024-08-05)

* Add `logfire.instrument_mysql()` by @aditkumar72 in https://github.com/pydantic/logfire/pull/341
* Set OTEL status description when logging exceptions by @alexmojaki in https://github.com/pydantic/logfire/pull/348
* Switch UpDownCounters to cumulative aggregation temporality by @alexmojaki in https://github.com/pydantic/logfire/pull/347
* Log more info about internal errors by @alexmojaki in https://github.com/pydantic/logfire/pull/346

## [v0.48.1] (2024-07-29)

* Handle newer opentelemetry versions by @alexmojaki in https://github.com/pydantic/logfire/pull/337
* More lenient handling of loguru message mismatch and better warnings by @alexmojaki in https://github.com/pydantic/logfire/pull/338
* Add better type hints for HTTPX and AsyncPG by @Kludex in https://github.com/pydantic/logfire/pull/342
* Handle `setuptools` changing `sys.path` for importing `packaging.version` by @alexmojaki in https://github.com/pydantic/logfire/pull/344

## [v0.48.0] (2024-07-24)

* Add `instrument_celery` method by @Kludex in https://github.com/pydantic/logfire/pull/322
* `capture_headers` by @alexmojaki in https://github.com/pydantic/logfire/pull/318
* Handle message formatting errors by @alexmojaki in https://github.com/pydantic/logfire/pull/329
* Handle logging `None` with `loguru` by @alexmojaki in https://github.com/pydantic/logfire/pull/331

## [v0.47.0] (2024-07-20)

* Fix recursive logging from OTEL's `BatchSpanProcessor` by @alexmojaki in https://github.com/pydantic/logfire/pull/306
* Set sqlalchemy 'connect' spans to debug level by @alexmojaki in https://github.com/pydantic/logfire/pull/307
* Add type hints to instrument methods by @Kludex in https://github.com/pydantic/logfire/pull/320
* Handle older versions of anthropic by @alexmojaki in https://github.com/pydantic/logfire/pull/316
* Update dependencies, handle change in importlib by @alexmojaki in https://github.com/pydantic/logfire/pull/323
* Summarize db.statement in message by @alexmojaki in https://github.com/pydantic/logfire/pull/308
* Handle and test other OpenAI/Anthropic  client methods by @alexmojaki in https://github.com/pydantic/logfire/pull/312

## [v0.46.1] (2024-07-05)

* Fix release process for `logfire-api` by @Kludex in https://github.com/pydantic/logfire/pull/303

## [v0.46.0] (2024-07-05)

* Add `logfire-api` by @Kludex in https://github.com/pydantic/logfire/pull/268
* Use exponential histogram buckets by @alexmojaki in https://github.com/pydantic/logfire/pull/282
* Add attribute noting details of scrubbed values by @alexmojaki in https://github.com/pydantic/logfire/pull/278
* Ensure `force_flush` at end of AWS Lambda invocation by @alexmojaki in https://github.com/pydantic/logfire/pull/296

## [v0.45.1] (2024-07-01)

* Fix ignore no config warning message by @ba1mn in https://github.com/pydantic/logfire/pull/292
* Ensure `StaticFiles` doesn't break `instrument_fastapi` by @alexmojaki in https://github.com/pydantic/logfire/pull/294

## [v0.45.0] (2024-06-29)

* Add `scrubbing: ScrubbingOptions | False` parameter to `logfire.configure`, replacing `scrubbing_patterns` and `scrubbing_callback` by @alexmojaki in https://github.com/pydantic/logfire/pull/283
* Fix and test unmapped SQLModels by @alexmojaki in https://github.com/pydantic/logfire/pull/286
* Optimize `collect_package_info` by @alexmojaki in https://github.com/pydantic/logfire/pull/285

## [v0.44.0] (2024-06-26)

* Prevent 'dictionary changed size during iteration' error in `install_auto_tracing` by @alexmojaki in https://github.com/pydantic/logfire/pull/277
* `suppress_instrumentation` when retrying exports by @alexmojaki in https://github.com/pydantic/logfire/pull/279
* Log async stack in `log_slow_async_callbacks` by @alexmojaki in https://github.com/pydantic/logfire/pull/280

## [v0.43.0] (2024-06-24)

* **BREAKING CHANGE**: Remove default for `modules` parameter of `install_auto_tracing` by @alexmojaki in https://github.com/pydantic/logfire/pull/261
* **BREAKING CHANGE**: Check if logfire token is valid in separate thread, so `logfire.configure` won't block startup and will no longer raise an exception for an invalid token, by @alexmojaki in https://github.com/pydantic/logfire/pull/274
* Remove `logfire_api_session` parameter from `logfire.configure` by @alexmojaki in https://github.com/pydantic/logfire/pull/272
* Default the log level to error if the status code is error, and vice versa by @alexmojaki in https://github.com/pydantic/logfire/pull/269
* Avoid importing `gitpython` by @alexmojaki in https://github.com/pydantic/logfire/pull/260
* Only delete files on `logfire clean` by @Kludex in https://github.com/pydantic/logfire/pull/267
* Bug fix: Logging arguments of a request to a FastAPI sub app by @sneakyPad in https://github.com/pydantic/logfire/pull/259
* Fix query params not being in message by @alexmojaki in https://github.com/pydantic/logfire/pull/271
* Replace 'Redacted' with 'Scrubbed' in 'Redacted due to...' by @alexmojaki in https://github.com/pydantic/logfire/pull/273

## [v0.42.0] (2024-06-11)

* Improved handling of request errors when exporting by @alexmojaki in https://github.com/pydantic/logfire/pull/252
* `ignore_no_config` setting added to `pyproject.toml` by @deepakdinesh1123 in https://github.com/pydantic/logfire/pull/254
* Make `logfire whoami` respect the `LOGFIRE_TOKEN` env var by @alexmojaki in https://github.com/pydantic/logfire/pull/256

## [v0.41.0] (2024-06-06)

* Fix backfill command by @alexmojaki in https://github.com/pydantic/logfire/pull/243
* Update Anthropic to use tools that are no longer in beta by @willbakst in https://github.com/pydantic/logfire/pull/249
    - Anthropic instrumentation now requires `anthropic>=0.27.0`

## [v0.40.0] (2024-06-04)

* **BREAKING CHANGE:** The `processors` parameter of `logfire.configure()` has been replaced by `additional_span_processors`. Passing `processors` will raise an error. Unlike `processors`, setting `additional_span_processors` to an empty sequence will not disable the default span processor which exports to Logfire. To do that, pass `send_to_logfire=False`. Similarly `metric_readers` has been replaced by `additional_metric_reader`. By @alexmojaki in https://github.com/pydantic/logfire/pull/233
* Improve error raised when opentelemetry.instrumentation.django is not installed by @deepakdinesh1123 in https://github.com/pydantic/logfire/pull/231
* Handle internal errors by @alexmojaki in https://github.com/pydantic/logfire/pull/232

## [v0.39.0] (2024-06-03)

Add new methods for easier integration in https://github.com/pydantic/logfire/pull/207:

* `instrument_flask`
* `instrument_starlette`
* `instrument_aiohttp_client`
* `instrument_sqlalchemy`
* `instrument_pymongo`
* `instrument_redis`

## [v0.38.0] (2024-05-31)

**BREAKING CHANGE**: Calling `logfire.info`, `logfire.error`, `logfire.span` etc. will no longer automatically configure logfire if it hasn't been configured already. Instead it will emit a warning and not log anything.
Users must call `logfire.configure()` before they want logging to actually start, even if they don't pass any arguments to `configure` and all configuration is done by environment variables.
Using integrations like `logfire.instrument_fastapi()` before calling `configure` will also emit a warning but it will still set up the instrumentation, although it will not log anything until `configure` is called.

## [v0.37.0] (2024-05-29)

* Add `logfire.suppress_instrumentation` context manager, silence `urllib3` debug logs from exporting by @jlondonobo in https://github.com/pydantic/logfire/pull/197

## [v0.36.1] (2024-05-27)

* Fix structlog import by @alexmojaki in https://github.com/pydantic/logfire/pull/217

## [v0.36.0] (2024-05-27)

* Allow passing OTEL kwargs through instrument_fastapi by @alexmojaki in https://github.com/pydantic/logfire/pull/205
* Retry connection errors by @alexmojaki in https://github.com/pydantic/logfire/pull/214

## [v0.35.0] (2024-05-21)

* Add `logfire.instrument_requests()` by @tlpinney in https://github.com/pydantic/logfire/pull/196
* Add `logfire.instrument_httpx()` by @tlpinney in https://github.com/pydantic/logfire/pull/198
* Add `logfire.instrument_django()` by @inspirsmith in https://github.com/pydantic/logfire/pull/200

## [v0.34.0] (2024-05-21)

* Allow instrumenting OpenAI/Anthropic client classes or modules by @alexmojaki in https://github.com/pydantic/logfire/pull/191

## [v0.33.0] (2024-05-18)

* Fix logging integrations with non-string messages by @alexmojaki in https://github.com/pydantic/logfire/pull/179
* Anthropic instrumentation by @willbakst in https://github.com/pydantic/logfire/pull/181

## [v0.32.1] (2024-05-15)

* Add 'executing' version to 'logfire info' output by @alexmojaki in https://github.com/pydantic/logfire/pull/180
* Don't use `include_url` with Pydantic's V1 `ValidationError` by @Kludex in https://github.com/pydantic/logfire/pull/184

## [v0.32.0] (2024-05-14)

* Don't scrub spans from OpenAI integration by @alexmojaki in https://github.com/pydantic/logfire/pull/173
* Convert FastAPI arguments log to span, don't set to debug by default by @alexmojaki in https://github.com/pydantic/logfire/pull/164
* Raise an exception when Pydantic plugin is enabled on Pydantic <2.5.0 by @bossenti in https://github.com/pydantic/logfire/pull/160
* Do not require project name on `logfire projects use` command by @Kludex in https://github.com/pydantic/logfire/pull/177

## [v0.31.0] (2024-05-13)

* Improve error when `opentelemetry-instrumentation-fastapi` is missing by @Kludex in https://github.com/pydantic/logfire/pull/143
* Set `send_to_logfire` to `False` when running under Pytest by @Kludex in https://github.com/pydantic/logfire/pull/154
* Add `logfire.metric_gauge()` by @Kludex in https://github.com/pydantic/logfire/pull/153
* Use `stack_info` instead of `stack_offset` by @Kludex in https://github.com/pydantic/logfire/pull/137
* Fix JSON encoding/schema of pydantic v1 models by @alexmojaki in https://github.com/pydantic/logfire/pull/163
* Handle intermediate logging/loguru levels by @alexmojaki in https://github.com/pydantic/logfire/pull/162
* Add exception on console by @Kludex in https://github.com/pydantic/logfire/pull/168
* f-string magic by @alexmojaki in https://github.com/pydantic/logfire/pull/151

## [v0.30.0] (2024-05-06)

* Close spans when process shuts down before the exporter shuts down and drops them by @alexmojaki in https://github.com/pydantic/logfire/pull/108
* add `psycopg` in OTEL_PACKAGES and optional-dependencies by @Elkiwa in https://github.com/pydantic/logfire/pull/115
* [PYD-877] Log OpenAI streaming response at the end instead of opening a span and attaching context in a generator that may not finish by @alexmojaki in https://github.com/pydantic/logfire/pull/107
* Increase minimum typing-extensions version by @Kludex in https://github.com/pydantic/logfire/pull/129
* Add note about creating write tokens when user is not authenticated by @Kludex in https://github.com/pydantic/logfire/pull/127
* Make pip install command printed by 'logfire inspect' easy to copy by @alexmojaki in https://github.com/pydantic/logfire/pull/130

## [v0.29.0] (2024-05-03)

* Add log level on `on_start` for ASGI send and receive messages by @Kludex in https://github.com/pydantic/logfire/pull/94
* Support a dataclass type as an argument by @dmontagu in https://github.com/pydantic/logfire/pull/100
* Add min_log_level to console options by @Kludex in https://github.com/pydantic/logfire/pull/95
* Improve the OpenAI integration by @Kludex in https://github.com/pydantic/logfire/pull/104

## [v0.28.3] (2024-05-02)

* Fix pydantic plugin for cloudpickle by @alexmojaki in https://github.com/pydantic/logfire/pull/86
* Handle unloaded SQLAlchemy fields in JSON schema by @alexmojaki in https://github.com/pydantic/logfire/pull/92

## [v0.28.2] (2024-05-02)

* Fix OpenAI streaming empty chunk error by @hramezani in https://github.com/pydantic/logfire/pull/69
* Update pyproject.toml to include logfire in sdist build target by @syniex in https://github.com/pydantic/logfire/pull/51
* Recommend `opentelemetry-instrumentation-sklearn` on `scikit-learn` instead of `sklearn` by @Kludex in https://github.com/pydantic/logfire/pull/75

## [v0.28.1] (2024-05-01)

* Don't scrub 'author' by @alexmojaki in https://github.com/pydantic/logfire/pull/55
* Check if object is SQLAlchemy before dataclass by @Kludex in https://github.com/pydantic/logfire/pull/67

## [v0.28.0] (2024-04-30)

* Add `logfire.instrument_asyncpg()` by @alexmojaki in https://github.com/pydantic/logfire/pull/44

## [v0.27.0] (2024-04-30)

First release from new repo!

* Update README by @Kludex in https://github.com/pydantic/logfire/pull/2
* Add linter & pipeline by @Kludex in https://github.com/pydantic/logfire/pull/1
* Use Python 3.8 for pipeline by @Kludex in https://github.com/pydantic/logfire/pull/3
* Use Rye instead of Poetry by @Kludex in https://github.com/pydantic/logfire/pull/5
* Add test suite by @Kludex in https://github.com/pydantic/logfire/pull/6
* Add custom PyPI by @Kludex in https://github.com/pydantic/logfire/pull/7
* Add release job by @Kludex in https://github.com/pydantic/logfire/pull/8
* Install rye on release job by @Kludex in https://github.com/pydantic/logfire/pull/9
* Add latest monorepo changes by @Kludex in https://github.com/pydantic/logfire/pull/10
* Add Python 3.12 to CI by @hramezani in https://github.com/pydantic/logfire/pull/11
* improve readme and related faff by @samuelcolvin in https://github.com/pydantic/logfire/pull/12
* CF pages docs build by @samuelcolvin in https://github.com/pydantic/logfire/pull/14
* Create alert docs by @Kludex in https://github.com/pydantic/logfire/pull/15
* improve the readme and contributing guide by @samuelcolvin in https://github.com/pydantic/logfire/pull/16
* Add classifiers by @hramezani in https://github.com/pydantic/logfire/pull/17
* tell rye to use uv by @samuelcolvin in https://github.com/pydantic/logfire/pull/19
* Adding docs for `instrument_openai` by @samuelcolvin in https://github.com/pydantic/logfire/pull/18
* Live view docs by @samuelcolvin in https://github.com/pydantic/logfire/pull/20
* Add `logfire info` and issue templates by @samuelcolvin in https://github.com/pydantic/logfire/pull/22
* Add GitHub discussions to help page, remove "login", show source link by @samuelcolvin in https://github.com/pydantic/logfire/pull/23
* setup coverage by @samuelcolvin in https://github.com/pydantic/logfire/pull/24
* improve coverage by @samuelcolvin in https://github.com/pydantic/logfire/pull/25
* Write token docs (#2244) by @Kludex in https://github.com/pydantic/logfire/pull/27
* add direct connect docs by @davidhewitt in https://github.com/pydantic/logfire/pull/26
* Add dashboard docs by @Kludex in https://github.com/pydantic/logfire/pull/28
* Add SQL Explore docs by @Kludex in https://github.com/pydantic/logfire/pull/29
* Make the `psycopg2` docs runnable as is by @Kludex in https://github.com/pydantic/logfire/pull/31
* Add Rye to installation by @Kludex in https://github.com/pydantic/logfire/pull/33
* Apply Logfire brand colors by @Kludex in https://github.com/pydantic/logfire/pull/32
* `logfire.instrument_psycopg()` function by @alexmojaki in https://github.com/pydantic/logfire/pull/30
* Handle recursive logging from OTEL by @alexmojaki in https://github.com/pydantic/logfire/pull/35
* Improve MongoDB docs by @Kludex in https://github.com/pydantic/logfire/pull/34
* Improve colors by @dmontagu in https://github.com/pydantic/logfire/pull/38
* Rename files to not have numeric prefixes by @dmontagu in https://github.com/pydantic/logfire/pull/39
* Handle cyclic references in JSON encoding and schema by @alexmojaki in https://github.com/pydantic/logfire/pull/37
* Ensure `logfire.testing` doesn't depend on pydantic and eval_type_backport by @alexmojaki in https://github.com/pydantic/logfire/pull/40
* Allow using pydantic plugin with models defined before calling logfire.configure by @alexmojaki in https://github.com/pydantic/logfire/pull/36

[v0.27.0]: https://github.com/pydantic/logfire/commits/v0.27.0
[v0.28.0]: https://github.com/pydantic/logfire/compare/v0.27.0...v0.28.0
[v0.28.1]: https://github.com/pydantic/logfire/compare/v0.28.0...v0.28.1
[v0.28.2]: https://github.com/pydantic/logfire/compare/v0.28.1...v0.28.2
[v0.28.3]: https://github.com/pydantic/logfire/compare/v0.28.2...v0.28.3
[v0.29.0]: https://github.com/pydantic/logfire/compare/v0.28.3...v0.29.0
[v0.30.0]: https://github.com/pydantic/logfire/compare/v0.29.0...v0.30.0
[v0.31.0]: https://github.com/pydantic/logfire/compare/v0.30.0...v0.31.0
[v0.32.0]: https://github.com/pydantic/logfire/compare/v0.31.0...v0.32.0
[v0.32.1]: https://github.com/pydantic/logfire/compare/v0.32.0...v0.32.1
[v0.33.0]: https://github.com/pydantic/logfire/compare/v0.32.1...v0.33.0
[v0.34.0]: https://github.com/pydantic/logfire/compare/v0.33.0...v0.34.0
[v0.35.0]: https://github.com/pydantic/logfire/compare/v0.34.0...v0.35.0
[v0.36.0]: https://github.com/pydantic/logfire/compare/v0.35.0...v0.36.0
[v0.36.1]: https://github.com/pydantic/logfire/compare/v0.36.0...v0.36.1
[v0.37.0]: https://github.com/pydantic/logfire/compare/v0.36.1...v0.37.0
[v0.38.0]: https://github.com/pydantic/logfire/compare/v0.37.0...v0.38.0
[v0.39.0]: https://github.com/pydantic/logfire/compare/v0.38.0...v0.39.0
[v0.40.0]: https://github.com/pydantic/logfire/compare/v0.39.0...v0.40.0
[v0.41.0]: https://github.com/pydantic/logfire/compare/v0.40.0...v0.41.0
[v0.42.0]: https://github.com/pydantic/logfire/compare/v0.41.0...v0.42.0
[v0.43.0]: https://github.com/pydantic/logfire/compare/v0.42.0...v0.43.0
[v0.44.0]: https://github.com/pydantic/logfire/compare/v0.43.0...v0.44.0
[v0.45.0]: https://github.com/pydantic/logfire/compare/v0.44.0...v0.45.0
[v0.45.1]: https://github.com/pydantic/logfire/compare/v0.45.0...v0.45.1
[v0.46.0]: https://github.com/pydantic/logfire/compare/v0.45.1...v0.46.0
[v0.46.1]: https://github.com/pydantic/logfire/compare/v0.46.0...v0.46.1
[v0.47.0]: https://github.com/pydantic/logfire/compare/v0.46.1...v0.47.0
[v0.48.0]: https://github.com/pydantic/logfire/compare/v0.47.0...v0.48.0
[v0.48.1]: https://github.com/pydantic/logfire/compare/v0.48.0...v0.48.1
[v0.49.0]: https://github.com/pydantic/logfire/compare/v0.48.1...v0.49.0
[v0.49.1]: https://github.com/pydantic/logfire/compare/v0.49.0...v0.49.1
[v0.50.0]: https://github.com/pydantic/logfire/compare/v0.49.1...v0.50.0
[v0.50.1]: https://github.com/pydantic/logfire/compare/v0.50.0...v0.50.1
[v0.51.0]: https://github.com/pydantic/logfire/compare/v0.50.1...v0.51.0
[v0.52.0]: https://github.com/pydantic/logfire/compare/v0.51.0...v0.52.0
[v0.53.0]: https://github.com/pydantic/logfire/compare/v0.52.0...v0.53.0
[v0.54.0]: https://github.com/pydantic/logfire/compare/v0.53.0...v0.54.0
[v0.55.0]: https://github.com/pydantic/logfire/compare/v0.54.0...v0.55.0
[v1.0.0]: https://github.com/pydantic/logfire/compare/v0.55.0...v1.0.0
[v1.0.1]: https://github.com/pydantic/logfire/compare/v1.0.0...v1.0.1
[v1.1.0]: https://github.com/pydantic/logfire/compare/v1.0.1...v1.1.0
[v1.2.0]: https://github.com/pydantic/logfire/compare/v1.1.0...v1.2.0
[v1.3.0]: https://github.com/pydantic/logfire/compare/v1.2.0...v1.3.0
[v1.3.1]: https://github.com/pydantic/logfire/compare/v1.3.0...v1.3.1
[v1.3.2]: https://github.com/pydantic/logfire/compare/v1.3.1...v1.3.2
[v2.0.0]: https://github.com/pydantic/logfire/compare/v1.3.2...v2.0.0
[v2.1.0]: https://github.com/pydantic/logfire/compare/v2.0.0...v2.1.0
[v2.1.1]: https://github.com/pydantic/logfire/compare/v2.1.0...v2.1.1
[v2.1.2]: https://github.com/pydantic/logfire/compare/v2.1.1...v2.1.2
[v2.2.0]: https://github.com/pydantic/logfire/compare/v2.1.2...v2.2.0
[v2.2.1]: https://github.com/pydantic/logfire/compare/v2.2.0...v2.2.1
[v2.3.0]: https://github.com/pydantic/logfire/compare/v2.2.1...v2.3.0
[v2.4.0]: https://github.com/pydantic/logfire/compare/v2.3.0...v2.4.0
[v2.4.1]: https://github.com/pydantic/logfire/compare/v2.4.0...v2.4.1
