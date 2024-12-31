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

logfire.info('Hello', data={
    'key_matching_my_pattern': 'This string will be redacted because its key matches',
    'other_key': 'This string will also be redacted because it matches MY_PATTERN case-insensitively',
    'password': 'This will be redacted because custom patterns are combined with the default patterns',
})
```

Here are the default scrubbing patterns:

`'password'`, `'passwd'`, `'mysql_pwd'`, `'secret'`, `'auth'`, `'credential'`, `'private[._ -]?key'`, `'api[._ -]?key'`,
`'session'`, `'cookie'`, `'csrf'`, `'xsrf'`, `'jwt'`, `'ssn'`, `'social[._ -]?security'`, `'credit[._ -]?card'`

## Scrubbing less with a callback

On the other hand, if the scrubbing is to aggressive, you can pass a function to [`callback`][logfire.ScrubbingOptions.callback] to prevent certain data from being redacted.

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

## Security tips

### Use message templates

The full span/log message is not scrubbed, only the fields within. For example, this:

```python
logfire.info('User details: {user}', user=User(id=123, password='secret'))
```

...may log something like:

```
User details: [Scrubbed due to 'password']
```

...but this:

```python
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
