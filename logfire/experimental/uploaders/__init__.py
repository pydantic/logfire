from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class UploadItem:
    """An item to upload."""

    key: str
    value: bytes
    media_type: str | None = None


class BaseUploader(ABC):
    """Abstract base class for uploaders."""

    @abstractmethod
    def upload(self, item: UploadItem) -> None:
        """Upload the given item."""

    @abstractmethod
    def get_attribute_value(self, key: str) -> Any:
        """Return a reference to the uploaded item, e.g. a URL or path."""
