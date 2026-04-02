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
      - ``azure``  — Azure Blob Storage container

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
    if backend == "azure":
        if not settings.blob_azure_container:
            raise ValueError(
                "blob_azure_container is required when blob_backend='azure'."
            )
        if not settings.blob_azure_connection_string and not settings.blob_azure_account_url:
            raise ValueError(
                "blob_azure_connection_string or blob_azure_account_url "
                "is required when blob_backend='azure'."
            )
        from app.storage.azure import AzureBlobStore

        return AzureBlobStore(
            container=settings.blob_azure_container,
            prefix=settings.blob_azure_prefix,
            connection_string=settings.blob_azure_connection_string,
            account_url=settings.blob_azure_account_url,
        )
    raise ValueError(
        f"Unknown blob_backend: {settings.blob_backend!r}. "
        "Supported: 'local', 's3', 'azure'."
    )
