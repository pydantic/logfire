# Pydantic Logfire

This distribution installs the [Pydantic Logfire](https://pydantic.dev/logfire)
Python SDK and command-line interface. The Python API is provided by
`logfire-sdk`. This package installs the `logfire` command, which runs the
Python CLI included in the SDK. The standalone `logfire-cli` package is not
installed as a dependency.

```bash
pip install logfire
```

The Python import is unchanged:

```python
import logfire
```

See the [Logfire documentation](https://pydantic.dev/docs/logfire/) to get
started.
