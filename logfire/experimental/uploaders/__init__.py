from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from logfire._internal.utils import sha256_bytes


@dataclass
class UploadItem:
    """An item to upload."""

    key: str
    value: bytes
    media_type: str | None = None

    @classmethod
    def create(cls, value: bytes, media_type: str | None = None) -> UploadItem:
        """Create an UploadItem with a generated key.

        Use this instead of constructing directly.
        """
        parts = [sha256_bytes(value)]
        if media_type:
            parts.insert(0, media_type)
        key = '/'.join(parts)
        return cls(key=key, value=value, media_type=media_type)


class BaseUploader(ABC):
    """Abstract base class for uploaders."""

    @abstractmethod
    def upload(self, item: UploadItem) -> None:
        """Upload the given item."""

    @abstractmethod
    def get_attribute_value(self, item: UploadItem) -> Any:
        """Return a reference to the uploaded item, e.g. a URL or path."""
