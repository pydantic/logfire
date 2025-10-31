from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass

from logfire._internal.constants import ONE_SECOND_IN_NANOSECONDS
from logfire._internal.utils import JsonValue, sha256_bytes


@dataclass
class UploadItem:
    """An item to upload."""

    key: str
    value: bytes
    media_type: str | None = None

    @classmethod
    def create(cls, value: bytes, *, timestamp: int | None, media_type: str | None = None) -> UploadItem:
        """Create an UploadItem with a generated key.

        Use this instead of constructing directly.
        """
        parts = [sha256_bytes(value)]

        if media_type:  # pragma: no branch
            parts.append(media_type)

        if timestamp is None:  # pragma: no cover
            date = datetime.date.today()
        else:
            date = datetime.datetime.fromtimestamp(timestamp / ONE_SECOND_IN_NANOSECONDS).date()
        parts.append(date.isoformat())

        key = '/'.join(parts[::-1])
        return cls(key=key, value=value, media_type=media_type)


class BaseUploader(ABC):
    """Abstract base class for uploaders."""

    @abstractmethod
    def upload(self, item: UploadItem) -> None:
        """Upload the given item."""

    @abstractmethod
    def get_attribute_value(self, item: UploadItem) -> JsonValue:
        """Return a reference to the uploaded item, e.g. a URL or path."""
