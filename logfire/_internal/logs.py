from __future__ import annotations

import dataclasses
import functools
from dataclasses import dataclass
from threading import Lock
from typing import Any
from weakref import WeakSet

from opentelemetry._logs import Logger, LoggerProvider, LogRecord, NoOpLoggerProvider
from opentelemetry.util.types import Attributes


@dataclass
class ProxyLoggerProvider(LoggerProvider):
    """A logger provider that wraps another internal logger provider allowing it to be re-assigned."""

    provider: LoggerProvider

    loggers: WeakSet[ProxyLogger] = dataclasses.field(default_factory=WeakSet)
    lock: Lock = dataclasses.field(default_factory=Lock)
    suppressed_scopes: set[str] = dataclasses.field(default_factory=set)

    def get_logger(
        self, name: str, version: str | None = None, schema_url: str | None = None, attributes: Attributes | None = None
    ) -> Logger:
        with self.lock:
            if name in self.suppressed_scopes:
                provider = NoOpLoggerProvider()
            else:
                provider = self.provider
            inner_logger = provider.get_logger(name, version, schema_url, attributes)
            logger = ProxyLogger(inner_logger, name, version, schema_url, attributes)
            self.loggers.add(logger)
            return logger

    def suppress_scopes(self, *scopes: str) -> None:
        with self.lock:
            self.suppressed_scopes.update(scopes)
            for logger in self.loggers:
                if logger.name in scopes:
                    logger.set_logger(NoOpLoggerProvider())

    def set_provider(self, logger_provider: LoggerProvider) -> None:
        with self.lock:
            self.provider = logger_provider
            for logger in self.loggers:
                logger.set_logger(NoOpLoggerProvider() if logger.name in self.suppressed_scopes else logger_provider)

    def __getattr__(self, item: str) -> Any:
        try:
            result = getattr(self.provider, item)
        except AttributeError:
            if item in ['shutdown', 'force_flush']:
                # These methods don't exist on the default NoOpLoggerProvider
                return lambda *_, **__: None  # type: ignore
            raise  # pragma: no cover

        if callable(result):

            @functools.wraps(result)
            def wrapper(*args: Any, **kwargs: Any):
                with self.lock:
                    return result(*args, **kwargs)

            return wrapper
        else:
            return result


@dataclass(eq=False)
class ProxyLogger(Logger):
    logger: Logger
    name: str
    version: str | None = None
    schema_url: str | None = None
    attributes: Attributes | None = None

    def emit(self, record: LogRecord) -> None:
        self.logger.emit(record)

    def set_logger(self, provider: LoggerProvider) -> None:
        self.logger = provider.get_logger(self.name, self.version, self.schema_url, self.attributes)

    def __getattr__(self, item: str):
        return getattr(self.logger, item)
