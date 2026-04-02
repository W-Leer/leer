"""Tests for blob storage abstraction, local/S3/Azure backends, and config wiring."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.storage.base import BlobRef, BlobStore, compute_sha256
from app.storage.factory import create_blob_store
from app.storage.local import LocalBlobStore
from app.storage.s3 import S3BlobStore
from app.storage.azure import AzureBlobStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def blob_dir(tmp_path: Path) -> Path:
    return tmp_path / "blobs"


@pytest.fixture()
def store(blob_dir: Path) -> LocalBlobStore:
    return LocalBlobStore(root=blob_dir)


# ---------------------------------------------------------------------------
# BlobRef
# ---------------------------------------------------------------------------


class TestBlobRef:
    def test_to_dict_roundtrip(self) -> None:
        ref = BlobRef(
            provider="local",
            key="runs/abc/art.json",
            size_bytes=42,
            content_type="application/json",
            sha256="deadbeef",
        )
        d = ref.to_dict()
        assert d["provider"] == "local"
        assert d["key"] == "runs/abc/art.json"
        assert d["size_bytes"] == 42
        assert d["content_type"] == "application/json"
        assert d["sha256"] == "deadbeef"
        assert "created_at" in d

    def test_frozen(self) -> None:
        ref = BlobRef(provider="local", key="k", size_bytes=0, content_type="", sha256="")
        with pytest.raises(AttributeError):
            ref.key = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# compute_sha256
# ---------------------------------------------------------------------------


class TestComputeSha256:
    def test_deterministic(self) -> None:
        data = b"hello world"
        assert compute_sha256(data) == compute_sha256(data)

    def test_known_value(self) -> None:
        import hashlib

        data = b"test"
        assert compute_sha256(data) == hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# LocalBlobStore — core operations
# ---------------------------------------------------------------------------


class TestLocalBlobStoreBasic:
    def test_protocol_conformance(self, store: LocalBlobStore) -> None:
        assert isinstance(store, BlobStore)

    def test_provider_name(self, store: LocalBlobStore) -> None:
        assert store.provider_name == "local"

    def test_put_and_get_roundtrip(self, store: LocalBlobStore) -> None:
        data = b'{"key": "value"}'
        ref = store.put("artifacts/a1.json", data)

        assert ref.provider == "local"
        assert ref.key == "artifacts/a1.json"
        assert ref.size_bytes == len(data)
        assert ref.sha256 == compute_sha256(data)
        assert ref.content_type == "application/json"

        assert store.get("artifacts/a1.json") == data

    def test_put_custom_content_type(self, store: LocalBlobStore) -> None:
        ref = store.put("file.bin", b"\x00\x01", content_type="application/octet-stream")
        assert ref.content_type == "application/octet-stream"

    def test_get_missing_raises(self, store: LocalBlobStore) -> None:
        with pytest.raises(FileNotFoundError):
            store.get("does/not/exist.json")

    def test_exists(self, store: LocalBlobStore) -> None:
        assert store.exists("a.json") is False
        store.put("a.json", b"x")
        assert store.exists("a.json") is True

    def test_delete_existing(self, store: LocalBlobStore) -> None:
        store.put("d.json", b"x")
        assert store.delete("d.json") is True
        assert store.exists("d.json") is False

    def test_delete_missing(self, store: LocalBlobStore) -> None:
        assert store.delete("nope.json") is False

    def test_overwrite(self, store: LocalBlobStore) -> None:
        store.put("ow.json", b"v1")
        store.put("ow.json", b"v2-longer")
        assert store.get("ow.json") == b"v2-longer"


# ---------------------------------------------------------------------------
# LocalBlobStore — nested keys
# ---------------------------------------------------------------------------


class TestLocalBlobStoreNestedKeys:
    def test_deeply_nested_key(self, store: LocalBlobStore) -> None:
        key = "runs/abc/steps/def/artifacts/stream.json"
        store.put(key, b"nested")
        assert store.get(key) == b"nested"
        assert store.exists(key)

    def test_sibling_keys(self, store: LocalBlobStore) -> None:
        store.put("dir/a.json", b"a")
        store.put("dir/b.json", b"b")
        assert store.get("dir/a.json") == b"a"
        assert store.get("dir/b.json") == b"b"


# ---------------------------------------------------------------------------
# LocalBlobStore — path safety
# ---------------------------------------------------------------------------


class TestLocalBlobStorePathSafety:
    def test_rejects_absolute_key(self, store: LocalBlobStore) -> None:
        with pytest.raises(ValueError, match="relative"):
            store.put("/etc/passwd", b"bad")

    def test_rejects_traversal(self, store: LocalBlobStore) -> None:
        with pytest.raises(ValueError, match="\\.\\."):
            store.put("../escape.json", b"bad")

    def test_rejects_mid_traversal(self, store: LocalBlobStore) -> None:
        with pytest.raises(ValueError, match="\\.\\."):
            store.put("runs/../../escape.json", b"bad")


# ---------------------------------------------------------------------------
# LocalBlobStore — large payload
# ---------------------------------------------------------------------------


class TestLocalBlobStoreLargePayload:
    def test_roundtrip_large_payload(self, store: LocalBlobStore) -> None:
        payload = json.dumps({"events": [{"i": i} for i in range(5000)]}).encode()
        ref = store.put("big.json", payload)
        assert ref.size_bytes == len(payload)
        assert store.get("big.json") == payload


# ---------------------------------------------------------------------------
# LocalBlobStore — root directory creation
# ---------------------------------------------------------------------------


class TestLocalBlobStoreRootCreation:
    def test_creates_root_on_init(self, tmp_path: Path) -> None:
        new_root = tmp_path / "deeply" / "nested" / "blobs"
        assert not new_root.exists()
        s = LocalBlobStore(root=new_root)
        assert s.root.exists()
        assert s.root.is_dir()


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_default_blob_settings(self) -> None:
        s = Settings(database_url="sqlite:///:memory:")
        assert s.blob_backend == "local"
        assert s.blob_local_root == ".leer/blobs"
        assert s.blob_inline_threshold_bytes == 256 * 1024


# ---------------------------------------------------------------------------
# Factory — create_blob_store
# ---------------------------------------------------------------------------


class TestCreateBlobStore:
    def test_creates_local_backend(self, tmp_path: Path) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="local",
            blob_local_root=str(tmp_path / "blobs"),
        )
        backend = create_blob_store(s)
        assert isinstance(backend, LocalBlobStore)
        assert isinstance(backend, BlobStore)
        assert backend.provider_name == "local"

    def test_local_backend_is_functional(self, tmp_path: Path) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="local",
            blob_local_root=str(tmp_path / "blobs"),
        )
        backend = create_blob_store(s)
        ref = backend.put("test.json", b'{"ok":true}')
        assert backend.get("test.json") == b'{"ok":true}'
        assert ref.size_bytes == len(b'{"ok":true}')

    def test_unknown_backend_raises(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="magic-cloud",
        )
        with pytest.raises(ValueError, match="magic-cloud"):
            create_blob_store(s)

    def test_case_insensitive_backend_name(self, tmp_path: Path) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="Local",
            blob_local_root=str(tmp_path / "blobs"),
        )
        backend = create_blob_store(s)
        assert isinstance(backend, LocalBlobStore)

    def test_creates_s3_backend(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="s3",
            blob_s3_bucket="my-bucket",
            blob_s3_region="us-east-1",
        )
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            backend = create_blob_store(s)
            assert isinstance(backend, S3BlobStore)
            assert backend.provider_name == "s3"

    def test_s3_missing_bucket_raises(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="s3",
        )
        with pytest.raises(ValueError, match="blob_s3_bucket"):
            create_blob_store(s)

    def test_case_insensitive_s3(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="S3",
            blob_s3_bucket="my-bucket",
        )
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            backend = create_blob_store(s)
            assert isinstance(backend, S3BlobStore)

    def test_unknown_backend_mentions_all(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="gcs",
        )
        with pytest.raises(ValueError, match="'local', 's3', 'azure'"):
            create_blob_store(s)


# ---------------------------------------------------------------------------
# S3BlobStore — helpers
# ---------------------------------------------------------------------------


class _FakeClientError(Exception):
    """Mimics botocore ClientError shape for tests without botocore installed."""

    def __init__(self, code: str) -> None:
        super().__init__(f"ClientError: {code}")
        self.response = {"Error": {"Code": code, "Message": "test"}}


@pytest.fixture()
def mock_s3_client() -> MagicMock:
    client = MagicMock()
    no_such_key = type("NoSuchKey", (Exception,), {})
    client.exceptions = MagicMock()
    client.exceptions.NoSuchKey = no_such_key
    return client


@pytest.fixture()
def s3_store(mock_s3_client: MagicMock) -> S3BlobStore:
    return S3BlobStore(bucket="test-bucket", client=mock_s3_client)


@pytest.fixture()
def s3_store_prefixed(mock_s3_client: MagicMock) -> S3BlobStore:
    return S3BlobStore(bucket="test-bucket", prefix="artifacts/", client=mock_s3_client)


# ---------------------------------------------------------------------------
# S3BlobStore — core operations
# ---------------------------------------------------------------------------


class TestS3BlobStoreBasic:
    def test_protocol_conformance(self, s3_store: S3BlobStore) -> None:
        assert isinstance(s3_store, BlobStore)

    def test_provider_name(self, s3_store: S3BlobStore) -> None:
        assert s3_store.provider_name == "s3"

    def test_put_calls_put_object(self, s3_store: S3BlobStore, mock_s3_client: MagicMock) -> None:
        data = b'{"key": "value"}'
        ref = s3_store.put("runs/abc/art.json", data)

        mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="runs/abc/art.json",
            Body=data,
            ContentType="application/json",
        )
        assert ref.provider == "s3"
        assert ref.key == "runs/abc/art.json"
        assert ref.size_bytes == len(data)
        assert ref.sha256 == compute_sha256(data)
        assert ref.content_type == "application/json"

    def test_put_custom_content_type(self, s3_store: S3BlobStore, mock_s3_client: MagicMock) -> None:
        ref = s3_store.put("f.bin", b"\x00\x01", content_type="application/octet-stream")
        assert ref.content_type == "application/octet-stream"
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "application/octet-stream"

    def test_get_returns_bytes(self, s3_store: S3BlobStore, mock_s3_client: MagicMock) -> None:
        body = MagicMock()
        body.read.return_value = b'{"ok": true}'
        mock_s3_client.get_object.return_value = {"Body": body}

        result = s3_store.get("runs/abc/art.json")

        mock_s3_client.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="runs/abc/art.json",
        )
        assert result == b'{"ok": true}'

    def test_get_missing_no_such_key(
        self, s3_store: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        mock_s3_client.get_object.side_effect = _FakeClientError("NoSuchKey")
        with pytest.raises(FileNotFoundError, match="runs/abc/art.json"):
            s3_store.get("runs/abc/art.json")

    def test_get_missing_404(
        self, s3_store: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        mock_s3_client.get_object.side_effect = _FakeClientError("404")
        with pytest.raises(FileNotFoundError, match="runs/abc/art.json"):
            s3_store.get("runs/abc/art.json")

    def test_get_access_denied_propagates(
        self, s3_store: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        err = _FakeClientError("AccessDenied")
        mock_s3_client.get_object.side_effect = err
        with pytest.raises(_FakeClientError) as exc_info:
            s3_store.get("runs/abc/art.json")
        assert exc_info.value is err

    def test_exists_true(self, s3_store: S3BlobStore, mock_s3_client: MagicMock) -> None:
        mock_s3_client.head_object.return_value = {}
        assert s3_store.exists("runs/abc/art.json") is True
        mock_s3_client.head_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="runs/abc/art.json",
        )

    def test_exists_false(self, s3_store: S3BlobStore, mock_s3_client: MagicMock) -> None:
        mock_s3_client.head_object.side_effect = _FakeClientError("404")
        assert s3_store.exists("nope.json") is False

    def test_delete_calls_delete_object(
        self, s3_store: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        result = s3_store.delete("runs/abc/art.json")
        assert result is True
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="runs/abc/art.json",
        )

    def test_delete_always_returns_true(
        self, s3_store: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        result = s3_store.delete("nonexistent.json")
        assert result is True


# ---------------------------------------------------------------------------
# S3BlobStore — prefix handling
# ---------------------------------------------------------------------------


class TestS3BlobStorePrefix:
    def test_prefix_prepended_to_put(
        self, s3_store_prefixed: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        s3_store_prefixed.put("runs/abc/art.json", b"data")
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "artifacts/runs/abc/art.json"

    def test_prefix_prepended_to_get(
        self, s3_store_prefixed: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        body = MagicMock()
        body.read.return_value = b"data"
        mock_s3_client.get_object.return_value = {"Body": body}

        s3_store_prefixed.get("runs/abc/art.json")
        call_kwargs = mock_s3_client.get_object.call_args[1]
        assert call_kwargs["Key"] == "artifacts/runs/abc/art.json"

    def test_prefix_prepended_to_exists(
        self, s3_store_prefixed: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        mock_s3_client.head_object.return_value = {}
        s3_store_prefixed.exists("runs/abc/art.json")
        call_kwargs = mock_s3_client.head_object.call_args[1]
        assert call_kwargs["Key"] == "artifacts/runs/abc/art.json"

    def test_prefix_prepended_to_delete(
        self, s3_store_prefixed: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        s3_store_prefixed.delete("runs/abc/art.json")
        call_kwargs = mock_s3_client.delete_object.call_args[1]
        assert call_kwargs["Key"] == "artifacts/runs/abc/art.json"

    def test_blob_ref_uses_logical_key(
        self, s3_store_prefixed: S3BlobStore, mock_s3_client: MagicMock
    ) -> None:
        ref = s3_store_prefixed.put("runs/abc/art.json", b"data")
        assert ref.key == "runs/abc/art.json"

    def test_prefix_without_trailing_slash(self, mock_s3_client: MagicMock) -> None:
        store = S3BlobStore(bucket="b", prefix="artifacts", client=mock_s3_client)
        store.put("k.json", b"x")
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "artifacts/k.json"

    def test_empty_prefix(self, mock_s3_client: MagicMock) -> None:
        store = S3BlobStore(bucket="b", prefix="", client=mock_s3_client)
        store.put("k.json", b"x")
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "k.json"


# ---------------------------------------------------------------------------
# S3BlobStore — config defaults
# ---------------------------------------------------------------------------


class TestS3ConfigDefaults:
    def test_s3_settings_defaults(self) -> None:
        s = Settings(database_url="sqlite:///:memory:")
        assert s.blob_s3_bucket is None
        assert s.blob_s3_region is None
        assert s.blob_s3_prefix == ""


# ===========================================================================
# Azure Blob Storage
# ===========================================================================


# ---------------------------------------------------------------------------
# Azure — helpers
# ---------------------------------------------------------------------------


class _FakeResourceNotFoundError(Exception):
    """Mimics azure ResourceNotFoundError for tests without azure SDK."""

    def __init__(self) -> None:
        super().__init__("BlobNotFound")

    @property
    def status_code(self) -> int:
        return 404

    @property
    def error_code(self) -> str:
        return "BlobNotFound"


# Make type(exc).__name__ == "ResourceNotFoundError" so _is_not_found works.
_FakeResourceNotFoundError.__name__ = "ResourceNotFoundError"  # type: ignore[attr-defined]


class _FakeAzureError(Exception):
    """Non-404 Azure error for propagation tests."""

    def __init__(self, code: str = "AuthorizationFailure") -> None:
        super().__init__(code)

    @property
    def status_code(self) -> int:
        return 403


@pytest.fixture()
def mock_azure_client() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def azure_store(mock_azure_client: MagicMock) -> AzureBlobStore:
    return AzureBlobStore(
        container="test-container",
        container_client=mock_azure_client,
    )


@pytest.fixture()
def azure_store_prefixed(mock_azure_client: MagicMock) -> AzureBlobStore:
    return AzureBlobStore(
        container="test-container",
        prefix="artifacts/",
        container_client=mock_azure_client,
    )


# ---------------------------------------------------------------------------
# AzureBlobStore — core operations
# ---------------------------------------------------------------------------


class TestAzureBlobStoreBasic:
    def test_protocol_conformance(self, azure_store: AzureBlobStore) -> None:
        assert isinstance(azure_store, BlobStore)

    def test_provider_name(self, azure_store: AzureBlobStore) -> None:
        assert azure_store.provider_name == "azure"

    def test_put_calls_upload_blob(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        data = b'{"key": "value"}'
        ref = azure_store.put("runs/abc/art.json", data)

        mock_azure_client.upload_blob.assert_called_once()
        call_kwargs = mock_azure_client.upload_blob.call_args
        assert call_kwargs[1]["name"] == "runs/abc/art.json"
        assert call_kwargs[1]["data"] == data
        assert call_kwargs[1]["overwrite"] is True
        assert ref.provider == "azure"
        assert ref.key == "runs/abc/art.json"
        assert ref.size_bytes == len(data)
        assert ref.sha256 == compute_sha256(data)
        assert ref.content_type == "application/json"

    def test_put_custom_content_type(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        ref = azure_store.put("f.bin", b"\x00\x01", content_type="application/octet-stream")
        assert ref.content_type == "application/octet-stream"

    def test_put_overwrite_always_true(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        azure_store.put("k.json", b"x")
        call_kwargs = mock_azure_client.upload_blob.call_args[1]
        assert call_kwargs["overwrite"] is True

    def test_get_returns_bytes(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        stream = MagicMock()
        stream.readall.return_value = b'{"ok": true}'
        mock_azure_client.download_blob.return_value = stream

        result = azure_store.get("runs/abc/art.json")

        mock_azure_client.download_blob.assert_called_once_with("runs/abc/art.json")
        assert result == b'{"ok": true}'

    def test_get_missing_raises_file_not_found(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        mock_azure_client.download_blob.side_effect = _FakeResourceNotFoundError()
        with pytest.raises(FileNotFoundError, match="runs/abc/art.json"):
            azure_store.get("runs/abc/art.json")

    def test_get_non_missing_error_propagates(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        err = _FakeAzureError()
        mock_azure_client.download_blob.side_effect = err
        with pytest.raises(_FakeAzureError) as exc_info:
            azure_store.get("runs/abc/art.json")
        assert exc_info.value is err

    def test_exists_true(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        mock_azure_client.get_blob_properties.return_value = {}
        assert azure_store.exists("runs/abc/art.json") is True
        mock_azure_client.get_blob_properties.assert_called_once_with("runs/abc/art.json")

    def test_exists_false(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        mock_azure_client.get_blob_properties.side_effect = _FakeResourceNotFoundError()
        assert azure_store.exists("nope.json") is False

    def test_exists_non_missing_error_propagates(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        err = _FakeAzureError()
        mock_azure_client.get_blob_properties.side_effect = err
        with pytest.raises(_FakeAzureError) as exc_info:
            azure_store.exists("runs/abc/art.json")
        assert exc_info.value is err

    def test_delete_existing(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        result = azure_store.delete("runs/abc/art.json")
        assert result is True
        mock_azure_client.delete_blob.assert_called_once_with("runs/abc/art.json")

    def test_delete_missing_returns_false(
        self, azure_store: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        mock_azure_client.delete_blob.side_effect = _FakeResourceNotFoundError()
        assert azure_store.delete("nope.json") is False


# ---------------------------------------------------------------------------
# AzureBlobStore — prefix handling
# ---------------------------------------------------------------------------


class TestAzureBlobStorePrefix:
    def test_prefix_prepended_to_put(
        self, azure_store_prefixed: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        azure_store_prefixed.put("runs/abc/art.json", b"data")
        call_kwargs = mock_azure_client.upload_blob.call_args[1]
        assert call_kwargs["name"] == "artifacts/runs/abc/art.json"

    def test_prefix_prepended_to_get(
        self, azure_store_prefixed: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        stream = MagicMock()
        stream.readall.return_value = b"data"
        mock_azure_client.download_blob.return_value = stream

        azure_store_prefixed.get("runs/abc/art.json")
        mock_azure_client.download_blob.assert_called_once_with("artifacts/runs/abc/art.json")

    def test_prefix_prepended_to_exists(
        self, azure_store_prefixed: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        mock_azure_client.get_blob_properties.return_value = {}
        azure_store_prefixed.exists("runs/abc/art.json")
        mock_azure_client.get_blob_properties.assert_called_once_with(
            "artifacts/runs/abc/art.json"
        )

    def test_prefix_prepended_to_delete(
        self, azure_store_prefixed: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        azure_store_prefixed.delete("runs/abc/art.json")
        mock_azure_client.delete_blob.assert_called_once_with("artifacts/runs/abc/art.json")

    def test_blob_ref_uses_logical_key(
        self, azure_store_prefixed: AzureBlobStore, mock_azure_client: MagicMock
    ) -> None:
        ref = azure_store_prefixed.put("runs/abc/art.json", b"data")
        assert ref.key == "runs/abc/art.json"

    def test_prefix_without_trailing_slash(self, mock_azure_client: MagicMock) -> None:
        store = AzureBlobStore(
            container="c", prefix="artifacts", container_client=mock_azure_client
        )
        store.put("k.json", b"x")
        call_kwargs = mock_azure_client.upload_blob.call_args[1]
        assert call_kwargs["name"] == "artifacts/k.json"

    def test_empty_prefix(self, mock_azure_client: MagicMock) -> None:
        store = AzureBlobStore(container="c", prefix="", container_client=mock_azure_client)
        store.put("k.json", b"x")
        call_kwargs = mock_azure_client.upload_blob.call_args[1]
        assert call_kwargs["name"] == "k.json"


# ---------------------------------------------------------------------------
# Azure — factory tests
# ---------------------------------------------------------------------------


class TestCreateBlobStoreAzure:
    def test_creates_azure_backend_with_connection_string(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="azure",
            blob_azure_container="my-container",
            blob_azure_connection_string="DefaultEndpointsProtocol=https;AccountName=test",
        )
        mock_cs = MagicMock()
        mock_module = MagicMock()
        mock_module.ContainerClient.from_connection_string.return_value = mock_cs
        with patch.dict("sys.modules", {"azure.storage.blob": mock_module}):
            backend = create_blob_store(s)
            assert isinstance(backend, AzureBlobStore)
            assert backend.provider_name == "azure"
            mock_module.ContainerClient.from_connection_string.assert_called_once()

    def test_creates_azure_backend_with_account_url(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="azure",
            blob_azure_container="my-container",
            blob_azure_account_url="https://myaccount.blob.core.windows.net",
        )
        mock_blob_module = MagicMock()
        mock_identity_module = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "azure.storage.blob": mock_blob_module,
                "azure.identity": mock_identity_module,
            },
        ):
            backend = create_blob_store(s)
            assert isinstance(backend, AzureBlobStore)
            assert backend.provider_name == "azure"

    def test_prefers_connection_string_over_account_url(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="azure",
            blob_azure_container="my-container",
            blob_azure_connection_string="DefaultEndpointsProtocol=https;AccountName=test",
            blob_azure_account_url="https://myaccount.blob.core.windows.net",
        )
        mock_module = MagicMock()
        mock_module.ContainerClient.from_connection_string.return_value = MagicMock()
        with patch.dict("sys.modules", {"azure.storage.blob": mock_module}):
            create_blob_store(s)
            mock_module.ContainerClient.from_connection_string.assert_called_once()

    def test_azure_missing_container_raises(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="azure",
            blob_azure_connection_string="DefaultEndpointsProtocol=https;AccountName=test",
        )
        with pytest.raises(ValueError, match="blob_azure_container"):
            create_blob_store(s)

    def test_azure_no_auth_raises(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="azure",
            blob_azure_container="my-container",
        )
        with pytest.raises(ValueError, match="blob_azure_connection_string or blob_azure_account_url"):
            create_blob_store(s)

    def test_case_insensitive_azure(self) -> None:
        s = Settings(
            database_url="sqlite:///:memory:",
            blob_backend="Azure",
            blob_azure_container="my-container",
            blob_azure_connection_string="DefaultEndpointsProtocol=https;AccountName=test",
        )
        mock_module = MagicMock()
        mock_module.ContainerClient.from_connection_string.return_value = MagicMock()
        with patch.dict("sys.modules", {"azure.storage.blob": mock_module}):
            backend = create_blob_store(s)
            assert isinstance(backend, AzureBlobStore)


# ---------------------------------------------------------------------------
# Azure — config defaults
# ---------------------------------------------------------------------------


class TestAzureConfigDefaults:
    def test_azure_settings_defaults(self) -> None:
        s = Settings(database_url="sqlite:///:memory:")
        assert s.blob_azure_container is None
        assert s.blob_azure_account_url is None
        assert s.blob_azure_connection_string is None
        assert s.blob_azure_prefix == ""
