"""Shared test configuration for blob storage tests."""

import tempfile

from app.storage.local import LocalBlobStore

# Single shared blob directory for all test modules.
SHARED_BLOB_DIR = tempfile.mkdtemp(prefix="leer-test-blobs-")
shared_blob_store = LocalBlobStore(root=SHARED_BLOB_DIR)
