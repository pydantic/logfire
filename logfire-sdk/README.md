# logfire-sdk

This distribution contains the Python software development kit (SDK) for
[Pydantic Logfire](https://pydantic.dev/logfire).

Most users should install `logfire`, which includes this SDK and the Logfire
command-line interface:

```bash
pip install logfire
```

Install `logfire-sdk` directly when the command-line interface is not needed or
is unavailable in the target runtime:

```bash
pip install logfire-sdk
```

The distribution name is `logfire-sdk`, but the Python import remains
`import logfire`. See the [SDK getting-started guide](https://pydantic.dev/docs/logfire/get-started/#sdk)
for usage and configuration guidance.
