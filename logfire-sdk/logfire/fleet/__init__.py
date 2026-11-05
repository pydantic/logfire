"""Logfire Fleet: manage this SDK's telemetry from Logfire.

Pass `fleet=True` (or a [`FleetOptions`][logfire.fleet.FleetOptions]) to
[`logfire.configure()`][logfire.configure], or set `LOGFIRE_FLEET=true`, and install the extra:

```bash
pip install 'logfire[fleet]'
```

The SDK then joins your Logfire Fleet over OpAMP (the Open Agent Management Protocol), and the
policy you set in Fleet applies to everything it sends: sampling, which signals are sent, log
levels, redaction and volume limits, on every exporter, the console included.
"""

from .._internal.fleet import FleetOptions

__all__ = ['FleetOptions']
