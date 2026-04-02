"""Tests for the blob offload write path (Step 3).

Validates threshold logic, blob writes, SQL NULL semantics,
size_bytes / sha256 population, and fetch endpoint integration.
"""

import json
import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.dependencies import get_blob_store
from app.main import app
from app.models import Artifact
from app.storage.base import compute_sha256

from tests.conftest import shared_blob_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_test_blob_store = shared_blob_store

# Low threshold for testing: 512 bytes
_TEST_THRESHOLD = 512


def _session_with_rollback():
    session: Session = next(get_session())
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _override_blob_store():
    return _test_blob_store


app.dependency_overrides[get_session] = _session_with_rollback
app.dependency_overrides[get_blob_store] = _override_blob_store
client = TestClient(app)


# ---------------------------------------------------------------------------
# Threshold override via env var
# ---------------------------------------------------------------------------


def _with_low_threshold():
    """Set a low threshold (512 bytes) via env var and clear settings cache."""
    os.environ["BLOB_INLINE_THRESHOLD_BYTES"] = str(_TEST_THRESHOLD)
    get_settings.cache_clear()


def _restore_threshold():
    """Restore default threshold."""
    os.environ.pop("BLOB_INLINE_THRESHOLD_BYTES", None)
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingest_with_artifact(inline_data: dict, *, artifact_type: str = "llm_request") -> dict:
    """Ingest a run with one artifact under the test threshold."""
    _with_low_threshold()

    slug = f"offload-{uuid.uuid4().hex[:8]}"
    run_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    art_id = str(uuid.uuid4())

    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "offload-test",
            "status": "completed",
            "trigger_type": "manual",
            "source": "sdk-python",
            "started_at": "2026-03-24T12:00:00Z",
            "ended_at": "2026-03-24T12:00:01Z",
            "metadata": {},
        },
        "steps": [
            {
                "id": step_id,
                "sequence_index": 0,
                "name": "test_step",
                "step_type": "llm",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00Z",
                "ended_at": "2026-03-24T12:00:01Z",
                "metadata": {},
            }
        ],
        "events": [],
        "artifacts": [
            {
                "id": art_id,
                "step_id": step_id,
                "artifact_type": artifact_type,
                "role": "output",
                "format": "json",
                "storage_kind": "inline",
                "sequence_index": 0,
                "mime_type": "application/json",
                "inline_data": inline_data,
                "preview_text": "offload test preview",
                "metadata": {},
            }
        ],
    }

    try:
        resp = client.post("/v1/ingest/runs", json=payload)
    finally:
        _restore_threshold()

    return {
        "status_code": resp.status_code,
        "body": resp.json(),
        "artifact_id": art_id,
        "run_id": run_id,
        "step_id": step_id,
        "slug": slug,
        "inline_data": inline_data,
    }


def _small_payload() -> dict:
    """Payload well under 512 bytes."""
    return {"model": "gpt-4.1", "text": "hello"}


def _large_payload() -> dict:
    """Payload well over 512 bytes."""
    return {"events": [{"index": i, "text": f"chunk number {i} with some content"} for i in range(50)]}


# ---------------------------------------------------------------------------
# Small artifact stays inline
# ---------------------------------------------------------------------------


def test_small_artifact_stays_inline():
    info = _ingest_with_artifact(_small_payload())
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.storage_kind == "inline"
        assert art.inline_data is not None
        assert art.blob_path is None
        assert art.preview_text == "offload test preview"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Large artifact becomes blob-backed
# ---------------------------------------------------------------------------


def test_large_artifact_becomes_blob():
    info = _ingest_with_artifact(_large_payload())
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.storage_kind == "blob"
        assert art.blob_path is not None
        assert art.preview_text == "offload test preview"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Blob file is actually written to storage
# ---------------------------------------------------------------------------


def test_blob_file_is_written():
    info = _ingest_with_artifact(_large_payload())
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert _test_blob_store.exists(art.blob_path)
        raw = _test_blob_store.get(art.blob_path)
        recovered = json.loads(raw)
        assert recovered == info["inline_data"]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# size_bytes and sha256 populated for BOTH inline and blob
# ---------------------------------------------------------------------------


def test_inline_artifact_has_size_and_hash():
    data = _small_payload()
    info = _ingest_with_artifact(data)
    assert info["status_code"] == 201

    expected_raw = json.dumps(data, separators=(",", ":")).encode()

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.size_bytes == len(expected_raw)
        assert art.sha256 == compute_sha256(expected_raw)
    finally:
        session.close()


def test_blob_artifact_has_size_and_hash():
    data = _large_payload()
    info = _ingest_with_artifact(data)
    assert info["status_code"] == 201

    expected_raw = json.dumps(data, separators=(",", ":")).encode()

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.size_bytes == len(expected_raw)
        assert art.sha256 == compute_sha256(expected_raw)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Blob-backed artifact resolves correctly through fetch endpoint
# ---------------------------------------------------------------------------


def test_blob_artifact_fetch_after_offload():
    data = _large_payload()
    info = _ingest_with_artifact(data)
    assert info["status_code"] == 201

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["storage_kind"] == "blob"
    assert body["data"] == data


# ---------------------------------------------------------------------------
# SQL NULL semantics are correct
# ---------------------------------------------------------------------------


def test_blob_artifact_has_sql_null_inline_data():
    """The DB row for a blob artifact must have real SQL NULL for inline_data,
    not JSONB null — otherwise the check constraint would have rejected it."""
    info = _ingest_with_artifact(_large_payload())
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        row = session.execute(text(
            "SELECT inline_data IS NULL AS is_null, blob_path IS NOT NULL AS has_blob "
            "FROM artifacts WHERE id = :id"
        ), {"id": info["artifact_id"]}).one()
        assert row.is_null is True
        assert row.has_blob is True
    finally:
        session.close()


def test_inline_artifact_has_sql_null_blob_path():
    info = _ingest_with_artifact(_small_payload())
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        row = session.execute(text(
            "SELECT blob_path IS NULL AS is_null, inline_data IS NOT NULL AS has_data "
            "FROM artifacts WHERE id = :id"
        ), {"id": info["artifact_id"]}).one()
        assert row.is_null is True
        assert row.has_data is True
    finally:
        session.close()


# ---------------------------------------------------------------------------
# preview_text preserved for both modes
# ---------------------------------------------------------------------------


def test_preview_preserved_for_inline():
    info = _ingest_with_artifact(_small_payload())
    assert info["status_code"] == 201

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.json()["preview_text"] == "offload test preview"


def test_preview_preserved_for_blob():
    info = _ingest_with_artifact(_large_payload())
    assert info["status_code"] == 201

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.json()["preview_text"] == "offload test preview"


# ---------------------------------------------------------------------------
# Threshold boundary: exactly equal to threshold stays inline
# ---------------------------------------------------------------------------


def _build_payload_of_size(target: int) -> dict:
    """Build a dict whose json.dumps(separators=(',',':')) is exactly target bytes."""
    base = {"x": ""}
    overhead = len(json.dumps(base, separators=(",", ":")).encode())
    pad_len = target - overhead
    if pad_len < 0:
        raise ValueError(f"Cannot build payload of {target} bytes, minimum overhead is {overhead}")
    base["x"] = "A" * pad_len
    raw = json.dumps(base, separators=(",", ":")).encode()
    assert len(raw) == target, f"Expected {target}, got {len(raw)}"
    return base


def test_exactly_at_threshold_stays_inline():
    payload = _build_payload_of_size(_TEST_THRESHOLD)
    info = _ingest_with_artifact(payload)
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.storage_kind == "inline"
    finally:
        session.close()


def test_one_byte_over_threshold_becomes_blob():
    payload = _build_payload_of_size(_TEST_THRESHOLD + 1)
    info = _ingest_with_artifact(payload)
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.storage_kind == "blob"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Blob key follows expected hierarchical pattern
# ---------------------------------------------------------------------------


def test_blob_key_is_hierarchical():
    info = _ingest_with_artifact(_large_payload())
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.blob_path is not None
        assert art.blob_path.startswith("projects/")
        assert "/runs/" in art.blob_path
        assert "/artifacts/" in art.blob_path
        assert art.blob_path.endswith(".json")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Timeline ref reflects offloaded storage_kind
# ---------------------------------------------------------------------------


def test_timeline_ref_reflects_blob_after_offload():
    info = _ingest_with_artifact(_large_payload(), artifact_type="llm_stream")
    assert info["status_code"] == 201

    resp = client.get(f"/v1/runs/{info['run_id']}/timeline")
    assert resp.status_code == 200

    ref = resp.json()["steps"][0]["artifacts"][0]
    assert ref["storage_kind"] == "blob"
    assert ref["size_bytes"] is not None
    assert ref["sha256"] is not None
