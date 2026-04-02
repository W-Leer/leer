"""Tests for the blob storage abstraction, local backend, and config wiring."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.config import Settings
from app.storage.base import BlobRef, BlobStore, compute_sha256
from app.storage.factory import create_blob_store
from app.storage.local import LocalBlobStore


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
