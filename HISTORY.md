# HISTORY

## v0.42.0 (2024-06-11)

## What's Changed

* Improved handling of request errors when exporting by @alexmojaki in https://github.com/pydantic/logfire/pull/252
* `ignore_no_config` setting added to `pyproject.toml` by @deepakdinesh1123 in https://github.com/pydantic/logfire/pull/254
* Make `logfire whoami` respect the `LOGFIRE_TOKEN` env var by @alexmojaki in https://github.com/pydantic/logfire/pull/256

## New Contributors
* @sydney-runkle made their first contribution in https://github.com/pydantic/logfire/pull/245

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.41.0...v0.42.0

## v0.41.0 (2024-06-06)

## What's Changed

* Fix backfill command by @alexmojaki in https://github.com/pydantic/logfire/pull/243
* Update Anthropic to use tools that are no longer in beta by @willbakst in https://github.com/pydantic/logfire/pull/249
  * NOTE: Anthropic instrumentation now requires `anthropic>=0.27.0`

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.40.0...v0.41.0

## v0.40.0 (2024-06-04)

## What's Changed

* **BREAKING CHANGE:** The `processors` parameter of `logfire.configure()` has been replaced by `additional_span_processors`. Passing `processors` will raise an error. Unlike `processors`, setting `additional_span_processors` to an empty sequence will not disable the default span processor which exports to Logfire. To do that, pass `send_to_logfire=False`. Similarly `metric_readers` has been replaced by `additional_metric_reader`. By @alexmojaki in https://github.com/pydantic/logfire/pull/233
* Improve error raised when opentelemetry.instrumentation.django is not installed by @deepakdinesh1123 in https://github.com/pydantic/logfire/pull/231
* Handle internal errors by @alexmojaki in https://github.com/pydantic/logfire/pull/232

## New Contributors
* @deepakdinesh1123 made their first contribution in https://github.com/pydantic/logfire/pull/231

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.39.0...v0.40.0

## v0.39.0 (2024-06-03)

## What's Changed

Add new methods for easier integration in https://github.com/pydantic/logfire/pull/207:

* `instrument_flask`
* `instrument_starlette`
* `instrument_aiohttp_client`
* `instrument_sqlalchemy`
* `instrument_pymongo`
* `instrument_redis`

## v0.38.0 (2024-05-31)

## What's Changed

**BREAKING CHANGE**: Calling `logfire.info`, `logfire.error`, `logfire.span` etc. will no longer automatically configure logfire if it hasn't been configured already. Instead it will emit a warning and not log anything.
Users must call `logfire.configure()` before they want logging to actually start, even if they don't pass any arguments to `configure` and all configuration is done by environment variables.
Using integrations like `logfire.instrument_fastapi()` before calling `configure` will also emit a warning but it will still set up the instrumentation, although it will not log anything until `configure` is called.

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.37.0...v0.38.0

## v0.37.0 (2024-05-29)

## What's Changed

* Add `logfire.suppress_instrumentation` context manager, silence `urllib3` debug logs from exporting by @jlondonobo in https://github.com/pydantic/logfire/pull/197

## New Contributors
* @jlondonobo made their first contribution in https://github.com/pydantic/logfire/pull/197

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.36.1...v0.37.0

## v0.36.1 (2024-05-27)

## What's Changed

* Fix structlog import by @alexmojaki in https://github.com/pydantic/logfire/pull/217


## v0.36.0 (2024-05-27)

## What's Changed

* Allow passing OTEL kwargs through instrument_fastapi by @alexmojaki in https://github.com/pydantic/logfire/pull/205
* Retry connection errors by @alexmojaki in https://github.com/pydantic/logfire/pull/214

## New Contributors
* @elisalimli made their first contribution in https://github.com/pydantic/logfire/pull/208
* @marcuslimdw made their first contribution in https://github.com/pydantic/logfire/pull/212

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.35.0...v0.36.0

## v0.35.0 (2024-05-21)

## What's Changed

* Add `logfire.instrument_requests()` by @tlpinney in https://github.com/pydantic/logfire/pull/196
* Add `logfire.instrument_httpx()` by @tlpinney in https://github.com/pydantic/logfire/pull/198
* Add `logfire.instrument_django()` by @inspirsmith in https://github.com/pydantic/logfire/pull/200

## New Contributors
* @tlpinney made their first contribution in https://github.com/pydantic/logfire/pull/196
* @inspirsmith made their first contribution in https://github.com/pydantic/logfire/pull/200

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.34.0...v0.35.0

## v0.34.0 (2024-05-21)

## What's Changed

* Allow instrumenting OpenAI/Anthropic client classes or modules by @alexmojaki in https://github.com/pydantic/logfire/pull/191

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.33.0...v0.34.0

## v0.33.0 (2024-05-18)

## What's Changed

* Fix logging integrations with non-string messages by @alexmojaki in https://github.com/pydantic/logfire/pull/179
* Anthropic instrumentation by @willbakst in https://github.com/pydantic/logfire/pull/181

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.32.1...v0.33.0

## v0.32.1 (2024-05-15)

## What's Changed
* Add 'executing' version to 'logfire info' output by @alexmojaki in https://github.com/pydantic/logfire/pull/180
* Don't use `include_url` with Pydantic's V1 `ValidationError` by @Kludex in https://github.com/pydantic/logfire/pull/184

---

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.32.0...v0.32.1

## v0.32.0 (2024-05-14)

## What's Changed
* Don't scrub spans from OpenAI integration by @alexmojaki in https://github.com/pydantic/logfire/pull/173
* Convert FastAPI arguments log to span, don't set to debug by default by @alexmojaki in https://github.com/pydantic/logfire/pull/164
* Raise an exception when Pydantic plugin is enabled on Pydantic <2.5.0 by @bossenti in https://github.com/pydantic/logfire/pull/160
* Do not require project name on `logfire projects use` command by @Kludex in https://github.com/pydantic/logfire/pull/177

---

## New Contributors
* @bossenti made their first contribution in https://github.com/pydantic/logfire/pull/160

---

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.31.0...v0.32.0

## v0.31.0 (2024-05-13)

## What's Changed
* Improve error when `opentelemetry-instrumentation-fastapi` is missing by @Kludex in https://github.com/pydantic/logfire/pull/143
* Set `send_to_logfire` to `False` when running under Pytest by @Kludex in https://github.com/pydantic/logfire/pull/154
* Add `logfire.metric_gauge()` by @Kludex in https://github.com/pydantic/logfire/pull/153
* Use `stack_info` instead of `stack_offset` by @Kludex in https://github.com/pydantic/logfire/pull/137
* Fix JSON encoding/schema of pydantic v1 models by @alexmojaki in https://github.com/pydantic/logfire/pull/163
* Handle intermediate logging/loguru levels by @alexmojaki in https://github.com/pydantic/logfire/pull/162
* Add exception on console by @Kludex in https://github.com/pydantic/logfire/pull/168
* f-string magic by @alexmojaki in https://github.com/pydantic/logfire/pull/151

---

## New Contributors
* @frankie567 made their first contribution in https://github.com/pydantic/logfire/pull/103
* @rishabgit made their first contribution in https://github.com/pydantic/logfire/pull/138
* @willbakst made their first contribution in https://github.com/pydantic/logfire/pull/140
* @KPCOFGS made their first contribution in https://github.com/pydantic/logfire/pull/148
* @hattajr made their first contribution in https://github.com/pydantic/logfire/pull/167

---

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.30.0...v0.31.0

## v0.30.0 (2024-05-06)

## What's Changed
* Close spans when process shuts down before the exporter shuts down and drops them by @alexmojaki in https://github.com/pydantic/logfire/pull/108
* add `psycopg` in OTEL_PACKAGES and optional-dependencies by @Elkiwa in https://github.com/pydantic/logfire/pull/115
* [PYD-877] Log OpenAI streaming response at the end instead of opening a span and attaching context in a generator that may not finish by @alexmojaki in https://github.com/pydantic/logfire/pull/107
* Increase minimum typing-extensions version by @Kludex in https://github.com/pydantic/logfire/pull/129
* Add note about creating write tokens when user is not authenticated by @Kludex in https://github.com/pydantic/logfire/pull/127
* Make pip install command printed by 'logfire inspect' easy to copy by @alexmojaki in https://github.com/pydantic/logfire/pull/130

## New Contributors
* @Elkiwa made their first contribution in https://github.com/pydantic/logfire/pull/115
* @eltociear made their first contribution in https://github.com/pydantic/logfire/pull/122

---

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.29.0...v0.30.0

## v0.29.0 (2024-05-03)

## What's Changed
* Add log level on `on_start` for ASGI send and receive messages by @Kludex in https://github.com/pydantic/logfire/pull/94
* Support a dataclass type as an argument by @dmontagu in https://github.com/pydantic/logfire/pull/100
* Add min_log_level to console options by @Kludex in https://github.com/pydantic/logfire/pull/95
* Improve the OpenAI integration by @Kludex in https://github.com/pydantic/logfire/pull/104

---

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.28.3...v0.29.0

## v0.28.3 (2024-05-02)

## What's Changed

* Fix pydantic plugin for cloudpickle by @alexmojaki in https://github.com/pydantic/logfire/pull/86
* Handle unloaded SQLAlchemy fields in JSON schema by @alexmojaki in https://github.com/pydantic/logfire/pull/92

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.28.2...v0.28.3

## v0.28.2 (2024-05-02)

## What's Changed
* Fix OpenAI streaming empty chunk error by @hramezani in https://github.com/pydantic/logfire/pull/69
* Update pyproject.toml to include logfire in sdist build target by @syniex in https://github.com/pydantic/logfire/pull/51
* Recommend `opentelemetry-instrumentation-sklearn` on `scikit-learn` instead of `sklearn` by @Kludex in https://github.com/pydantic/logfire/pull/75

## New Contributors
* @syniex made their first contribution in https://github.com/pydantic/logfire/pull/51

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.28.1...v0.28.2

## v0.28.1 (2024-05-01)

## What's Changed
* Don't scrub 'author' by @alexmojaki in https://github.com/pydantic/logfire/pull/55
* Check if object is SQLAlchemy before dataclass by @Kludex in https://github.com/pydantic/logfire/pull/67

---

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.28.0...v0.28.1

## v0.28.0 (2024-04-30)

## What's Changed

* Add `logfire.instrument_asyncpg()` by @alexmojaki in https://github.com/pydantic/logfire/pull/44

**Full Changelog**: https://github.com/pydantic/logfire/compare/v0.27.0...v0.28.0

## v0.27.0 (2024-04-30)

First release from new repo!

## What's Changed

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

**Full Changelog**: https://github.com/pydantic/logfire/commits/v0.27.0
