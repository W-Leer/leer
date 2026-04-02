"""Local filesystem blob store for development."""

from __future__ import annotations

import os
from pathlib import Path

from app.storage.base import BlobRef, compute_sha256


class LocalBlobStore:
    """Blob store backed by a local directory.

    Suitable for development and single-node deployments.
    NOT intended for production multi-server use.
    """

    _provider = "local"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def provider_name(self) -> str:
        return self._provider

    @property
    def root(self) -> Path:
        return self._root

    # -- write ----------------------------------------------------------------

    def put(self, key: str, data: bytes, *, content_type: str = "application/json") -> BlobRef:
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return BlobRef(
            provider=self._provider,
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            sha256=compute_sha256(data),
        )

    # -- read -----------------------------------------------------------------

    def get(self, key: str) -> bytes:
        dest = self._resolve(key)
        if not dest.is_file():
            raise FileNotFoundError(f"Blob not found: {key}")
        return dest.read_bytes()

    # -- delete ---------------------------------------------------------------

    def delete(self, key: str) -> bool:
        dest = self._resolve(key)
        if not dest.is_file():
            return False
        dest.unlink()
        return True

    # -- exists ---------------------------------------------------------------

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    # -- internal -------------------------------------------------------------

    def _resolve(self, key: str) -> Path:
        """Resolve *key* to a safe filesystem path under root.

        Prevents path traversal by rejecting absolute paths and '..' segments.
        """
        if os.path.isabs(key):
            raise ValueError(f"Blob key must be relative: {key}")
        normalized = Path(key)
        if ".." in normalized.parts:
            raise ValueError(f"Blob key must not contain '..': {key}")
        return self._root / normalized
