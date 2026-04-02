"""Shared FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.storage.base import BlobStore
from app.storage.factory import create_blob_store


@lru_cache
def _blob_store_singleton() -> BlobStore:
    return create_blob_store(get_settings())


def get_blob_store() -> BlobStore:
    """FastAPI dependency that returns the configured blob store.

    Uses a cached singleton so the store is created once per process.
    Override this dependency in tests to inject a test-local store.
    """
    return _blob_store_singleton()
