"""Build a BlobStore backend from application settings."""

from __future__ import annotations

from app.config import Settings
from app.storage.base import BlobStore
from app.storage.local import LocalBlobStore


def create_blob_store(settings: Settings) -> BlobStore:
    """Construct the configured blob storage backend.

    Currently supports:
      - ``local``  — filesystem-backed (default, suitable for dev)

    Raises ``ValueError`` for unknown backend names.
    """
    backend = settings.blob_backend.lower()
    if backend == "local":
        return LocalBlobStore(root=settings.blob_local_root)
    raise ValueError(
        f"Unknown blob_backend: {settings.blob_backend!r}. "
        "Supported: 'local'."
    )
