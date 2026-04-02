"""Build a BlobStore backend from application settings."""

from __future__ import annotations

from app.config import Settings
from app.storage.base import BlobStore
from app.storage.local import LocalBlobStore


def create_blob_store(settings: Settings) -> BlobStore:
    """Construct the configured blob storage backend.

    Currently supports:
      - ``local``  — filesystem-backed (default, suitable for dev)
      - ``s3``     — AWS S3 bucket

    Raises ``ValueError`` for unknown backend names.
    """
    backend = settings.blob_backend.lower()
    if backend == "local":
        return LocalBlobStore(root=settings.blob_local_root)
    if backend == "s3":
        if not settings.blob_s3_bucket:
            raise ValueError(
                "blob_s3_bucket is required when blob_backend='s3'."
            )
        from app.storage.s3 import S3BlobStore

        return S3BlobStore(
            bucket=settings.blob_s3_bucket,
            prefix=settings.blob_s3_prefix,
            region=settings.blob_s3_region,
        )
    raise ValueError(
        f"Unknown blob_backend: {settings.blob_backend!r}. "
        "Supported: 'local', 's3'."
    )
