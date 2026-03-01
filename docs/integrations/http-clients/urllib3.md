---
title: "Logfire urllib3 Integration: Setup Guide"
description: Learn how to use the logfire.instrument_urllib3() method to instrument urllib3 with Logfire.
integration: otel
---
# urllib3

The [`logfire.instrument_urllib3()`][logfire.Logfire.instrument_urllib3] method can be used to
instrument [`urllib3`][urllib3] with **Logfire**.

## Installation

Install `logfire` with the `urllib3` extra:

{{ install_logfire(extras=['urllib3']) }}

## Usage

```py title="main.py" skip-run="true" skip-reason="external-connection"
import urllib3

import logfire

logfire.configure()
logfire.instrument_urllib3()

http = urllib3.PoolManager()
http.request('GET', 'https://httpbin.org/get')
```

[`logfire.instrument_urllib3()`][logfire.Logfire.instrument_urllib3] uses the
**OpenTelemetry urllib3 Instrumentation** package,
which you can find more information about [here][opentelemetry-urllib3].

[opentelemetry-urllib3]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/urllib3/urllib3.html
[urllib3]: https://urllib3.readthedocs.io/
