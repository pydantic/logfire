from opentelemetry.instrumentation.requests import RequestsInstrumentor


def instrument_requests():
    """Instrument the `requests` module so that spans are automatically created for each request.

    See the `Logfire.instrument_requests` method for details.
    """
    RequestsInstrumentor().instrument()  # type: ignore[reportUnknownMemberType]
