---
title: "Logfire: Guide for Scrubbing Sensitive Data from Logs"
description: "Learn how to use Logfire to keep logs & sensitive data safe: Automatically scan spans & logs to scrub data like passwords, tokens & PII before exporting."
---
# Scrubbing sensitive data

The **Logfire** SDK scans for and redacts potentially sensitive data from logs and spans before exporting them.

## Disabling scrubbing

To disable scrubbing entirely, set [`scrubbing`][logfire.configure(scrubbing)] to `False`:

```python
import logfire

logfire.configure(scrubbing=False)
```

## Scrubbing more with custom patterns

By default, the SDK looks for some sensitive regular expressions. To add your own patterns, set [`extra_patterns`][logfire.ScrubbingOptions.extra_patterns] to a list of regex strings:

```python
import logfire

logfire.configure(scrubbing=logfire.ScrubbingOptions(extra_patterns=['my_pattern']))

logfire.info(
    'Hello',
    data={
        'key_matching_my_pattern': 'This string will be redacted because its key matches',
        'other_key': 'This string will also be redacted because it matches MY_PATTERN case-insensitively',
        'password': 'This will be redacted because custom patterns are combined with the default patterns',
    },
)
```

Here are the default scrubbing patterns. The keys are the names you pass to
[`disabled_patterns`][logfire.ScrubbingOptions.disabled_patterns]:

```python
{
    'password': 'password',
    'passwd': 'passwd',
    'mysql_pwd': 'mysql_pwd',
    'secret': 'secret',
    'auth': 'auth(?!ors?\\b)',
    'credential': 'credential',
    'private_key': 'private[._ -]?key',
    'api_key': 'api[._ -]?key',
    'session': 'session',
    'cookie': 'cookie',
    'social_security': 'social[._ -]?security',
    'credit_card': 'credit[._ -]?card',
    'logfire_token': 'logfire[._ -]?token',
    'pylf_token': 'pylf_v\\d+_',
    'csrf': '(?:\\b|_)csrf(?:\\b|_)',
    'xsrf': '(?:\\b|_)xsrf(?:\\b|_)',
    'jwt': '(?:\\b|_)jwt(?:\\b|_)',
    'ssn': '(?:\\b|_)ssn(?:\\b|_)',
}
```

## Scrubbing less

If the scrubbing is too aggressive, there are three ways to hold it back, from broadest to narrowest.
Reach for the narrowest one that solves your problem.

### Turning off a default pattern

Pass the name of a default pattern to [`disabled_patterns`][logfire.ScrubbingOptions.disabled_patterns]
to stop applying it. The names are the keys of the table above.

```python
import logfire

logfire.configure(scrubbing=logfire.ScrubbingOptions(disabled_patterns=['session']))

logfire.info('Hello', session_id='abc123')  # no longer redacted
```

This turns the pattern off everywhere, so it is the bluntest of the three. Passing a name that isn't
a default pattern raises an error rather than being quietly ignored.

Two patterns cannot be disabled: `logfire_token` and `pylf_token`. They guard the write token
Logfire itself uses, which would otherwise be recorded in your spans and sent to Logfire, where
anyone with read access to your project could read it.

### Marking an attribute as safe

If the problem is one attribute rather than one pattern, name it in
[`safe_keys`][logfire.ScrubbingOptions.safe_keys]:

```python
import logfire

logfire.configure(scrubbing=logfire.ScrubbingOptions(safe_keys=['auth_types']))

logfire.info('Hello', auth_types=['BASIC', 'BEARER'], authorization='Bearer hunter2')
# auth_types is kept; authorization is still redacted
```

A safe key is matched **exactly**, at **every nesting depth**, and exempts **everything nested
underneath it**. So `safe_keys=['request']` keeps a password nested inside `request` as well. Only
use it for keys whose contents are always safe to send.

### Making an exception for specific values

When the pattern and the attribute are both worth keeping and only certain values are false
positives, pass a function to [`callback`][logfire.ScrubbingOptions.callback]. It is called for every
match. Return `None` (or nothing) to let the redaction happen, or return a value to use instead —
usually `match.value`, the original.

The function takes one argument of type [`logfire.ScrubMatch`][logfire.ScrubMatch], which carries:

- `path` — where the value sits in the span, e.g. `('attributes', 'session_id')`
- `value` — the value about to be redacted
- `pattern_match` — the [`re.Match`][re.Match] object; `pattern_match.group(0)` is the text that triggered it

Exempt one specific attribute:

```python
import logfire


def scrubbing_callback(match: logfire.ScrubMatch):
    # `my_safe_value` often contains the string 'password' but it's not actually sensitive.
    if match.path == ('attributes', 'my_safe_value') and match.pattern_match.group(0) == 'password':
        # Return the original value to prevent redaction.
        return match.value


logfire.configure(scrubbing=logfire.ScrubbingOptions(callback=scrubbing_callback))
```

Exempt an attribute name wherever it appears, however deeply nested:

```python
import logfire


def scrubbing_callback(match: logfire.ScrubMatch):
    if match.path[-1] in {'session_id', 'user_session'}:
        return match.value


logfire.configure(scrubbing=logfire.ScrubbingOptions(callback=scrubbing_callback))
```

Keep only values you recognise, and redact the rest:

```python
import logfire


def scrubbing_callback(match: logfire.ScrubMatch):
    if match.path[-1] == 'auth_type' and match.value in {'BASIC', 'BEARER'}:
        return match.value


logfire.configure(scrubbing=logfire.ScrubbingOptions(callback=scrubbing_callback))
```

Returning a value stops Logfire looking inside it, so returning `match.value` for a key that holds a
dict keeps that whole dict as-is — nothing nested within it is scrubbed. Return a narrower value if
that isn't what you want.

## Security tips

### Use message templates

The full span/log message is not scrubbed, only the fields within. For example, this:

```python skip="true" skip-reason="incomplete"
logfire.info('User details: {user}', user=User(id=123, password='secret'))
```

...may log something like:

```
User details: [Scrubbed due to 'password']
```

...but this:

```python skip="true" skip-reason="incomplete"
user = User(id=123, password='secret')
logfire.info('User details: ' + str(user))
```

will log:

```
User details: User(id=123, password='secret')
```

This is necessary so that safe messages such as 'Password is correct' are not redacted completely.

Using f-strings (e.g. `logfire.info(f'User details: {user}')`) *is* safe if `inspect_arguments` is enabled (the default in Python 3.11+) and working correctly.
[See here](../guides/onboarding-checklist/add-manual-tracing.md#f-strings) for more information.

In short, don't format the message yourself. This is also a good practice in general for [other reasons](../guides/onboarding-checklist/add-manual-tracing.md#messages-and-span-names).

### Keep sensitive data out of URLs

The attribute `"http.url"` which is recorded by OpenTelemetry instrumentation libraries is considered safe so that URLs like `"http://example.com/users/123/authenticate"` are not redacted.

As a general rule, not just for Logfire, assume that URLs (including query parameters) will be logged, so sensitive data should be put in the request body or headers instead.

### Use parameterized database queries

The `"db.statement"` attribute which is recorded by OpenTelemetry database instrumentation libraries is considered safe so that SQL queries like `"SELECT secret_value FROM table WHERE ..."` are not redacted.

Use parameterized queries (e.g. prepared statements) so that sensitive data is not interpolated directly into the query string, even if
you use an interpolation method that's safe from SQL injection.

### LLM and AI messages

Scrubbing is **disabled** for LLM message attributes such as `gen_ai.input.messages`, `gen_ai.output.messages`, and `pydantic_ai.all_messages`. This is intentional because:

1. **False positives**: LLMs frequently produce content containing words like "password" or "secret" in normal conversation (e.g., "Your password has been reset" or "The secret to success is..."), which would trigger false positives.
2. **Ineffective detection**: LLMs might output sensitive data without using any keywords that regex-based scrubbing could detect.

Because of these limitations, if your LLM interactions might contain sensitive data, the recommended approach is to **exclude message content from logging entirely** rather than relying on scrubbing. For example, with [Pydantic AI](../integrations/llms/pydanticai.md):

```python skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_pydantic_ai(include_content=False)
```

This will still log spans for LLM calls and agent runs with timing and metadata, but will exclude the actual prompts, completions, and tool call arguments/responses.
