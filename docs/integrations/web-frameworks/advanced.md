---
integration: advanced
---

# Gunicorn

[Gunicorn](https://docs.gunicorn.org/en/latest/index.html) is a Python WSGI HTTP server for UNIX.
It is a pre-fork worker model, which means it forks multiple worker processes to handle requests concurrently.

To configure Logfire with Gunicorn, you can use [post_fork hook](https://docs.gunicorn.org/en/latest/settings.html#post-fork):

```py
import logfire

def post_fork(server, worker):
    logfire.configure()
```
