---
title: "Send traces from PHP"
description: "Send traces from a PHP application to Logfire using the standard OpenTelemetry SDK."
---

# PHP

See what your PHP application is doing in Logfire: the requests it handles, how long each one took, and which ones failed. This takes about five minutes.

PHP does not have a dedicated Logfire SDK, but Logfire is built on [OpenTelemetry (OTel)](https://opentelemetry.io/), the open industry standard for collecting traces, metrics, and logs. The standard OpenTelemetry PHP SDK sends data straight to Logfire once you point it at the right endpoint, and you get **traces** (the full journey of one request, made of nested **spans**, where a span is one unit of work with a name, a start, and a duration) in the Logfire UI.

## Before you start

You need:

- A Logfire project and a **write token** (the credential your app uses to send data to a Logfire project). Copy one from **Project → Settings → Write tokens**; see [Create Write Tokens](../how-to-guides/create-write-tokens.md).
- PHP 8.1 or newer and [Composer](https://getcomposer.org/).

!!! note "This sends your data to Logfire"
    The steps below send your app's data to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](../how-to-guides/alternative-backends.md) instead. Your write token is a secret, so keep it out of source control.

## Send your first trace

**1. Install the OpenTelemetry packages**

```sh
composer require open-telemetry/sdk open-telemetry/exporter-otlp php-http/guzzle7-adapter
```

The OTLP exporter needs an HTTP client; `php-http/guzzle7-adapter` provides one.

**2. Configure the exporter**

```sh
export OTEL_PHP_AUTOLOAD_ENABLED=true
export OTEL_SERVICE_NAME=hello-php
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

With `OTEL_PHP_AUTOLOAD_ENABLED=true`, the SDK builds a tracer provider from these variables when your app loads and flushes it automatically when the script ends. The endpoint above is for the US [data region](../reference/data-regions.md); use `https://logfire-eu.pydantic.dev` for the EU region.

**3. Add the code**

```php title="hello.php"
<?php
require __DIR__ . '/vendor/autoload.php';

\OpenTelemetry\API\Globals::tracerProvider()
    ->getTracer('hello-php')
    ->spanBuilder('Hello World')
    ->startSpan()
    ->end();
```

**4. Run it**

```sh
php hello.php
```

## See it in the Live view

Open the [**Live view**](../guides/web-ui/live.md) in Logfire. Your `Hello World` span appears as it arrives:

![Traces arriving in the Logfire Live view](../images/logfire-live-view.png)

Each row is one span, with its service, name, and duration. The screenshot shows a busier app; your run appears as its own row, service `hello-php` and span `Hello World`, which you can click to open the full trace.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `composer require` or the run fails: no PSR-18 HTTP client found | The OTLP exporter needs an HTTP client that isn't installed | Install `php-http/guzzle7-adapter` (or another PSR-18 client) |
| The script runs but nothing appears | Autoloading is off, so no tracer provider is built | Set `OTEL_PHP_AUTOLOAD_ENABLED=true` |
| Nothing arrives from a self-hosted instance with a private certificate | PHP's HTTP client does not trust the private CA, and the OpenTelemetry certificate variable is ignored | Set `openssl.cafile=/path/to/ca.pem` in your `php.ini` (or pass `php -d openssl.cafile=/path/to/ca.pem`) |

## Next steps

- **New to tracing?** [Core concepts](../concepts.md) explains spans and traces and how to read them.
- **Want automatic traces?** Add the [`ext-opentelemetry` extension](https://opentelemetry.io/docs/zero-code/php/) and the matching `open-telemetry/opentelemetry-auto-*` packages to instrument your framework, HTTP clients, and database calls with no code changes.
- **Another language?** See [Language support](../instrument/index.md), or [Alternative clients](../how-to-guides/alternative-clients.md) for the generic pattern.
