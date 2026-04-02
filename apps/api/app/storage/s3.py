"""AWS S3 blob store for production deployments."""

from __future__ import annotations

from typing import Any

from app.storage.base import BlobRef, compute_sha256


class S3BlobStore:
    """Blob store backed by an AWS S3 bucket.

    Uses the boto3 S3 client for all operations.  Auth follows the standard
    boto3 credential chain (env vars, shared config, IAM role, etc.).

    ``delete()`` uses S3's idempotent semantics — ``delete_object`` succeeds
    even when the key does not exist, so this method always returns ``True``.
    This differs from ``LocalBlobStore`` which returns ``False`` for missing
    keys.  The return value of ``delete`` is not used for correctness anywhere
    in Leer, so the simpler single-call approach is preferred.
    """

    _provider = "s3"

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix.strip("/") else ""
        if client is not None:
            self._client = client
        else:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 is required for the S3 blob backend. "
                    "Install it with:  pip install boto3"
                ) from None
            self._client = boto3.client("s3", region_name=region)

    @property
    def provider_name(self) -> str:
        return self._provider

    def _full_key(self, key: str) -> str:
        """Prepend the configured prefix to a logical key."""
        return f"{self._prefix}{key}"

    # -- write ----------------------------------------------------------------

    def put(self, key: str, data: bytes, *, content_type: str = "application/json") -> BlobRef:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._full_key(key),
            Body=data,
            ContentType=content_type,
        )
        return BlobRef(
            provider=self._provider,
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            sha256=compute_sha256(data),
        )

    # -- read -----------------------------------------------------------------

    def get(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(
                Bucket=self._bucket,
                Key=self._full_key(key),
            )
        except self._client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Blob not found in S3: {key}")
        return resp["Body"].read()

    # -- delete ---------------------------------------------------------------

    def delete(self, key: str) -> bool:
        self._client.delete_object(
            Bucket=self._bucket,
            Key=self._full_key(key),
        )
        return True

    # -- exists ---------------------------------------------------------------

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=self._full_key(key),
            )
            return True
        except Exception as exc:
            if hasattr(exc, "response"):
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchKey"):
                    return False
            raise
