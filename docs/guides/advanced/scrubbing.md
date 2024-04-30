# Scrubbing sensitive data

The **Logfire** SDK scans for and redacts potentially sensitive data from logs and spans before exporting them.

## Scrubbing more with custom patterns

By default, the SDK looks for some sensitive regular expressions. To add your own patterns, set [`scrubbing_patterns`][logfire.configure(scrubbing_patterns)] to a list of regex strings:

```python
import logfire

logfire.configure(scrubbing_patterns=['my_pattern'])

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

On the other hand, if the scrubbing is to aggressive, you can pass a function to [`scrubbing_callback`][logfire.configure(scrubbing_callback)] to prevent certain data from being redacted.

The function will be called for each potential match found by the scrubber. If it returns `None`, the value is redacted. Otherwise, the returned value replaces the matched value. The function accepts a single argument of type [`logfire.ScrubMatch`][logfire.ScrubMatch].

Here's an example:

```python
import logfire

def scrubbing_callback(match: logfire.ScrubMatch):
    # OpenTelemetry database instrumentation libraries conventionally
    # use `db.statement` as the attribute key for SQL queries.
    # Assume that SQL queries are safe even if they contain words like 'password'.
    # Make sure you always use SQL parameters instead of formatting strings directly!
    if match.path == ('attributes', 'db.statement'):
        # Return the original value to prevent redaction.
        return match.value

logfire.configure(scrubbing_callback=scrubbing_callback)
```

## Security tips

### Use message templates

The full span/log message is not scrubbed, only the fields within. For example, this:

```python
logfire.info('User details: {user}', user=User(id=123, password='secret'))
```

...may log something like:

```
User details: [Redacted due to 'password']
```

...but this:

```python
user = User(id=123, password='secret')
logfire.info(f'User details: {user}')
```

will log:

```
User details: User(id=123, password='secret')
```

This is necessary so that safe messages such as 'Password is correct' are not redacted completely.

In short, don't use f-strings or otherwise format the message yourself. This is also a good practice in general for non-security reasons.

### Keep sensitive data out URLs

The attribute `"http.url"` which is recorded by OpenTelemetry instrumentation libraries is considered safe so that URLs like `"http://example.com/users/123/authenticate"` are not redacted.

As a general rule, not just for Logfire, assume that URLs (including query parameters) will be logged, so sensitive data should be put in the request body or headers instead.
