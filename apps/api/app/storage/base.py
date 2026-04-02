"""Provider-agnostic blob storage abstraction for Leer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class BlobRef:
    """Canonical reference returned after writing a blob.

    Contains enough information to persist alongside an artifact record
    and later retrieve, verify, or delete the blob.
    """

    provider: str
    key: str
    size_bytes: int
    content_type: str
    sha256: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "key": self.key,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "created_at": self.created_at.isoformat(),
        }


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@runtime_checkable
class BlobStore(Protocol):
    """Minimal provider-agnostic blob storage interface."""

    @property
    def provider_name(self) -> str:
        """Short identifier for this backend (e.g. 'local', 's3', 'gcs', 'azure')."""
        ...

    def put(self, key: str, data: bytes, *, content_type: str = "application/json") -> BlobRef:
        """Write *data* under *key* and return a canonical reference."""
        ...

    def get(self, key: str) -> bytes:
        """Return the raw bytes for *key*.

        Raises ``FileNotFoundError`` when the key does not exist.
        """
        ...

    def delete(self, key: str) -> bool:
        """Delete *key*.  Return True if deleted, False if it didn't exist."""
        ...

    def exists(self, key: str) -> bool:
        """Return True if *key* exists in the store."""
        ...
