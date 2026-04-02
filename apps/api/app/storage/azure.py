"""Azure Blob Storage backend for production deployments."""

from __future__ import annotations

from typing import Any

from app.storage.base import BlobRef, compute_sha256


class AzureBlobStore:
    """Blob store backed by an Azure Blob Storage container.

    Auth priority:
      1. Connection string (if provided)
      2. Account URL + ``DefaultAzureCredential``

    ``delete()`` returns ``False`` when the blob does not exist, matching
    ``LocalBlobStore`` semantics.
    """

    _provider = "azure"

    def __init__(
        self,
        container: str,
        prefix: str = "",
        *,
        account_url: str | None = None,
        connection_string: str | None = None,
        container_client: Any | None = None,
    ) -> None:
        self._prefix = prefix.rstrip("/") + "/" if prefix.strip("/") else ""

        if container_client is not None:
            self._client = container_client
            return

        try:
            from azure.storage.blob import ContainerClient
        except ImportError:
            raise ImportError(
                "azure-storage-blob is required for the Azure blob backend. "
                "Install it with:  pip install azure-storage-blob azure-identity"
            ) from None

        if connection_string:
            self._client = ContainerClient.from_connection_string(
                connection_string,
                container_name=container,
            )
        elif account_url:
            from azure.identity import DefaultAzureCredential

            self._client = ContainerClient(
                account_url=account_url,
                container_name=container,
                credential=DefaultAzureCredential(),
            )
        else:
            raise ValueError(
                "Azure blob backend requires either "
                "blob_azure_connection_string or blob_azure_account_url."
            )

    @property
    def provider_name(self) -> str:
        return self._provider

    def _full_key(self, key: str) -> str:
        """Prepend the configured prefix to a logical key."""
        return f"{self._prefix}{key}"

    # -- write ----------------------------------------------------------------

    def put(self, key: str, data: bytes, *, content_type: str = "application/json") -> BlobRef:
        try:
            from azure.storage.blob import ContentSettings
        except ImportError:
            ContentSettings = None  # type: ignore[assignment,misc]

        upload_kwargs: dict[str, Any] = {"overwrite": True}
        if ContentSettings is not None:
            upload_kwargs["content_settings"] = ContentSettings(content_type=content_type)

        self._client.upload_blob(
            name=self._full_key(key),
            data=data,
            **upload_kwargs,
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
            stream = self._client.download_blob(self._full_key(key))
            return stream.readall()
        except Exception as exc:
            if _is_not_found(exc):
                raise FileNotFoundError(f"Blob not found in Azure: {key}") from exc
            raise

    # -- delete ---------------------------------------------------------------

    def delete(self, key: str) -> bool:
        try:
            self._client.delete_blob(self._full_key(key))
            return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise

    # -- exists ---------------------------------------------------------------

    def exists(self, key: str) -> bool:
        try:
            self._client.get_blob_properties(self._full_key(key))
            return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise


def _is_not_found(exc: Exception) -> bool:
    """Duck-typed check for Azure ResourceNotFoundError without hard import."""
    cls_name = type(exc).__name__
    if cls_name == "ResourceNotFoundError":
        return True
    if hasattr(exc, "status_code") and exc.status_code == 404:
        return True
    if hasattr(exc, "error_code") and exc.error_code == "BlobNotFound":
        return True
    return False
