# Logfire NOOP

This is a NOOP (No Operation) module for Logfire.

It's meant to be used by third-party packages that should no-op in case logfire is not installed.

## Usage

```python
try:
    import logfire
except ImportError:
    import logfire_noop as logfire
```
