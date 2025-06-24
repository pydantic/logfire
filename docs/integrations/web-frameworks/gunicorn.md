---
integration: otel
---

# Gunicorn

[Gunicorn](https://docs.gunicorn.org/en/latest/index.html) is a Python WSGI HTTP server for UNIX.
It is a pre-fork worker model, which means it forks multiple worker processes to handle requests concurrently.

To configure Logfire with Gunicorn, you can use the `logfire.configure()` function to set up Logfire in the
[`post_fork` hook](https://docs.gunicorn.org/en/latest/settings.html#post-fork) in Gunicorn's configuration file:

```py
import logfire

def post_fork(server, worker):
    logfire.configure()
```

Then start Gunicorn with the configuration file:

```bash
gunicorn myapp:app --config gunicorn_config.py
```

Where `myapp:app` is your WSGI application and `gunicorn_config.py` is the configuration file where you defined the `post_fork` function.
