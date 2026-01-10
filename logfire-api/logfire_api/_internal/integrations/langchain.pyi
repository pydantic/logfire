import logfire
from contextlib import AbstractContextManager

def instrument_langchain(logfire_instance: logfire.Logfire) -> AbstractContextManager[None]: ...
