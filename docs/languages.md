---
title: "Pydantic Logfire: Supported Languages"
description: "Logfire has first-party SDKs for Python, TypeScript, and Rust, and works with any other language through OpenTelemetry."
---
Logfire is built on [OpenTelemetry (OTel)](https://opentelemetry.io/), the open industry standard for collecting traces, metrics, and logs. That means Logfire works with every language OpenTelemetry supports.

## First-party SDKs

These SDKs wrap OpenTelemetry in a native API for each language:

- [Python](https://github.com/pydantic/logfire)
- [JavaScript/TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/)
- [Rust](languages/rust.md)

## Other languages via OpenTelemetry

For a language without a dedicated SDK, you send data with the standard OpenTelemetry SDK. We have setup guides for:

- [Go](languages/go.md)
- [.NET](languages/dotnet.md)
- [Java](languages/java.md)

For any other language, see [Alternative clients](how-to-guides/alternative-clients.md).
