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

Here are the default scrubbing patterns:

```python
[
    'password',
    'passwd',
    'mysql_pwd',
    'secret',
    'auth(?!ors?\\b)',
    'credential',
    'private[._ -]?key',
    'passphrase',
    '(?:signing|hmac)[._ -]?key',
    'api[._ -]?key',
    'session',
    'cookie',
    'social[._ -]?security',
    'credit[._ -]?card',
    'logfire[._ -]?token',
    '(?:access|refresh|bearer|(?:\\b|_)id)[._ -]?token',
    'security[._ -]?token',
    'pylf_v\\d+_',
    '(?:\\b|_)csrf(?:\\b|_)',
    '(?:\\b|_)xsrf(?:\\b|_)',
    '(?:\\b|_)jwt(?:\\b|_)',
    '(?:\\b|_)ssn(?:\\b|_)',
]
```

## Scrubbing less with a callback

On the other hand, if the scrubbing is too aggressive, you can pass a function to [`callback`][logfire.ScrubbingOptions.callback] to prevent certain data from being redacted.

The function will be called for each potential match found by the scrubber. If it returns `None`, the value is redacted. Otherwise, the returned value replaces the matched value. The function accepts a single argument of type [`logfire.ScrubMatch`][logfire.ScrubMatch].

Here's an example:

```python
import logfire


def scrubbing_callback(match: logfire.ScrubMatch):
    # `my_safe_value` often contains the string 'password' but it's not actually sensitive.
    if match.path == ('attributes', 'my_safe_value') and match.pattern_match.group(0) == 'password':
        # Return the original value to prevent redaction.
        return match.value


logfire.configure(scrubbing=logfire.ScrubbingOptions(callback=scrubbing_callback))
```

Logfire scrubs a value before checking whether its key matches a pattern. This includes strings and values inside dictionaries, lists, and JSON-encoded containers. Your callback for a matching key receives the scrubbed value, so it can return that value unchanged or return a subset of a container. If it returns a different value, Logfire uses that replacement without scrubbing it again. Values under safe keys remain exempt from scrubbing.

If the callback returns a string unchanged (or returns an equal string of the same type), Logfire checks later positions in the same key or string value for other matches. A different returned string is used as the final value. After 100 allowed matches in one string, Logfire redacts the value to limit the search cost.

!!! warning "Keep scrubbing callbacks simple and pure"

    Base your callback on the match and any configuration that is safe to share across threads.
    Request-local values, such as values stored in a Python `ContextVar`, may be unavailable on the background thread.
    The callback should not have side effects.
    Do not mutate `match.value` in place. Logfire may not detect the change, so the mutated value may not be written back.
    If the callback raises an exception, Logfire logs the error and redacts the matched value as though the callback returned `None`. Scrubbing then continues.
    It should return quickly, as it can get called many times.

## Masking part of a string

Use [`transform_string`][logfire.ScrubbingOptions.transform_string] to replace sensitive text while keeping the rest of a value. The callback receives the string and its path:

```python
import re

import logfire
from logfire.types import StringValue


def mask_email(item: StringValue) -> str:
    if '@' not in item.value:
        return item.value
    return re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[email]', item.value)


logfire.configure(scrubbing=logfire.ScrubbingOptions(transform_string=mask_email))
logfire.info('Contact {email}', email='alice@example.com')
```

The exported `email` attribute and formatted message contain `[email]`. The callback runs on string values inside JSON and under keys that are exempt from pattern matching. Pattern matching runs on the returned string where permitted.

The callback runs for every string the scrubber reaches, including large values. Keep it fast, and test any regex you use against long inputs. The email regex above is illustrative and can be expensive on long strings.

!!! warning "Keep values redacted if masking fails"

    If `transform_string` raises an exception, Logfire logs the error and keeps the original string. Pattern matching still runs where permitted, but a value such as an email address may be exported unchanged. To prevent that, catch errors inside your callback and return a redacted string such as `'[redacted]'`.

## When Logfire scrubs spans

Scrubbing span attributes is slow, so it happens in a background thread when possible.
It will instead happen on the calling thread if any of the following are true:

- Console logging is enabled and prints attributes, i.e. `include_attributes` is `True`, or it is unset and `verbose` is `True`.
- A span processor is included in `additional_span_processors` that implements an `on_end` hook and isn't a `BatchSpanProcessor`.

Message template fields are always scrubbed on the calling thread during message formatting.

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
