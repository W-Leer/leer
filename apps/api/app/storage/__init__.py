from app.storage.base import BlobRef, BlobStore
from app.storage.factory import create_blob_store
from app.storage.local import LocalBlobStore

__all__ = ["BlobRef", "BlobStore", "LocalBlobStore", "S3BlobStore", "create_blob_store"]


def __getattr__(name: str):
    if name == "S3BlobStore":
        from app.storage.s3 import S3BlobStore

        return S3BlobStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
