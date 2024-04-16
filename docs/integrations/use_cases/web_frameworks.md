# Web Frameworks

Here are some tips for instrumenting your web applications.

## Integrations

If you're using one of the following libraries, check out the integration docs:

- [FastAPI](../fastapi.md)
- [Starlette](../starlette.md)
- [Django](../django.md)
- [Flask](../flask.md)

Otherwise, check if your server uses [WSGI](../wsgi.md) or [ASGI](../asgi.md) and check the corresponding integration.

## Capturing HTTP server request and response headers

There are three environment variables to tell the OpenTelemetry instrumentation libraries to capture request and response headers:

- `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`
- `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE`
- `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS`

Each accepts a comma-separated list of regexes which are checked case-insensitively against header names. The first two determine which request/response headers are captured and added to span attributes. The third determines which headers will have their values redacted.

For example, to capture _all_ headers, set the following:

```
OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST=".*"
OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE=".*"
```

To specifically capture the `content-type` request header and request headers starting with `X-`:

```
OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="content-type,X-.*"
```

To replace the `Authorization` header value with `[REDACTED]` to avoid leaking user credentials:

```
OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS="Authorization"
```
