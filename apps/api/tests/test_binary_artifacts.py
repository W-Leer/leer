"""Tests for binary/media artifact pipeline (Step 1 — binary artifact transport).

Covers:
- Ingest binary artifact via binary_data_b64
- Binary artifact becomes blob-backed with correct size_bytes / sha256
- Binary content endpoint returns raw bytes with correct Content-Type
- JSON endpoint returns metadata without data for binary artifacts
- Missing artifact / missing blob returns clean errors
- Timeline refs include mime_type
- Existing JSON artifacts still behave as before
"""

import base64
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

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
# Helpers
# ---------------------------------------------------------------------------

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
_PDF_BYTES = b"%PDF-1.4 " + b"\x00" * 300


def _ingest_binary_artifact(
    *,
    data: bytes = _PNG_BYTES,
    mime_type: str = "image/png",
    artifact_type: str = "user_upload",
    role: str = "input",
    preview_text: str | None = "binary preview",
    filename: str | None = "test.png",
) -> dict:
    slug = f"bin-{uuid.uuid4().hex[:8]}"
    run_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    art_id = str(uuid.uuid4())

    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "binary-test",
            "status": "completed",
            "trigger_type": "manual",
            "source": "sdk-python",
            "started_at": "2026-04-05T12:00:00Z",
            "ended_at": "2026-04-05T12:00:01Z",
            "metadata": {},
        },
        "steps": [
            {
                "id": step_id,
                "sequence_index": 0,
                "name": "upload",
                "step_type": "tool",
                "status": "completed",
                "started_at": "2026-04-05T12:00:00Z",
                "ended_at": "2026-04-05T12:00:01Z",
                "metadata": {},
            }
        ],
        "events": [],
        "artifacts": [
            {
                "id": art_id,
                "step_id": step_id,
                "artifact_type": artifact_type,
                "role": role,
                "format": "binary",
                "storage_kind": "blob",
                "sequence_index": 0,
                "mime_type": mime_type,
                "filename": filename,
                "inline_data": None,
                "preview_text": preview_text,
                "metadata": {},
                "binary_data_b64": base64.b64encode(data).decode("ascii"),
            }
        ],
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    return {
        "status_code": resp.status_code,
        "body": resp.json(),
        "artifact_id": art_id,
        "run_id": run_id,
        "step_id": step_id,
        "slug": slug,
        "raw_bytes": data,
    }


def _ingest_json_artifact(*, inline_data: dict | None = None) -> dict:
    slug = f"json-{uuid.uuid4().hex[:8]}"
    run_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    art_id = str(uuid.uuid4())

    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "json-test",
            "status": "completed",
            "trigger_type": "manual",
            "source": "sdk-python",
            "started_at": "2026-04-05T12:00:00Z",
            "ended_at": "2026-04-05T12:00:01Z",
            "metadata": {},
        },
        "steps": [
            {
                "id": step_id,
                "sequence_index": 0,
                "name": "llm_call",
                "step_type": "llm",
                "status": "completed",
                "started_at": "2026-04-05T12:00:00Z",
                "ended_at": "2026-04-05T12:00:01Z",
                "metadata": {},
            }
        ],
        "events": [],
        "artifacts": [
            {
                "id": art_id,
                "step_id": step_id,
                "artifact_type": "llm_request",
                "role": "input",
                "format": "json",
                "storage_kind": "inline",
                "sequence_index": 0,
                "mime_type": "application/json",
                "inline_data": inline_data or {"model": "gpt-4.1"},
                "preview_text": "json preview",
                "metadata": {},
            }
        ],
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201
    return {"artifact_id": art_id, "run_id": run_id, "step_id": step_id}


# ---------------------------------------------------------------------------
# Binary artifact ingest succeeds
# ---------------------------------------------------------------------------


def test_ingest_binary_artifact_succeeds():
    info = _ingest_binary_artifact()
    assert info["status_code"] == 201


# ---------------------------------------------------------------------------
# Binary artifact is blob-backed in DB
# ---------------------------------------------------------------------------


def test_binary_artifact_is_blob_backed():
    info = _ingest_binary_artifact()
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.storage_kind == "blob"
        assert art.blob_path is not None
        assert art.inline_data is None
    finally:
        session.close()


# ---------------------------------------------------------------------------
# size_bytes and sha256 populated
# ---------------------------------------------------------------------------


def test_binary_artifact_has_size_and_sha256():
    info = _ingest_binary_artifact()
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.size_bytes == len(_PNG_BYTES)
        assert art.sha256 == compute_sha256(_PNG_BYTES)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# mime_type preserved
# ---------------------------------------------------------------------------


def test_binary_artifact_mime_type_preserved():
    info = _ingest_binary_artifact(mime_type="application/pdf", data=_PDF_BYTES)
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.mime_type == "application/pdf"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Binary content endpoint returns correct bytes and Content-Type
# ---------------------------------------------------------------------------


def test_binary_content_endpoint_returns_raw_bytes():
    info = _ingest_binary_artifact(data=_PNG_BYTES, mime_type="image/png")
    assert info["status_code"] == 201

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}/content")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == _PNG_BYTES


def test_binary_content_endpoint_pdf():
    info = _ingest_binary_artifact(data=_PDF_BYTES, mime_type="application/pdf")
    assert info["status_code"] == 201

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}/content")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == _PDF_BYTES


# ---------------------------------------------------------------------------
# JSON endpoint returns metadata but no data for binary artifacts
# ---------------------------------------------------------------------------


def test_json_endpoint_for_binary_artifact_returns_no_data():
    info = _ingest_binary_artifact()
    assert info["status_code"] == 201

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["artifact_type"] == "user_upload"
    assert body["format"] == "binary"
    assert body["mime_type"] == "image/png"
    assert body["storage_kind"] == "blob"
    assert body["filename"] == "test.png"
    assert body["size_bytes"] == len(_PNG_BYTES)
    assert body["sha256"] == compute_sha256(_PNG_BYTES)
    assert body["data"] is None


# ---------------------------------------------------------------------------
# JSON artifacts still work as before
# ---------------------------------------------------------------------------


def test_json_artifact_still_works():
    info = _ingest_json_artifact(inline_data={"model": "gpt-4.1", "temp": 0.7})

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["data"] == {"model": "gpt-4.1", "temp": 0.7}
    assert body["storage_kind"] == "inline"
    assert body["mime_type"] == "application/json"


def test_json_content_endpoint_returns_json():
    info = _ingest_json_artifact(inline_data={"key": "value"})

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}/content")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert resp.json() == {"key": "value"}


# ---------------------------------------------------------------------------
# Missing artifact returns 404
# ---------------------------------------------------------------------------


def test_missing_artifact_returns_404():
    resp = client.get(f"/v1/artifacts/{uuid.uuid4()}")
    assert resp.status_code == 404

    resp = client.get(f"/v1/artifacts/{uuid.uuid4()}/content")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Missing blob returns clean error
# ---------------------------------------------------------------------------


def test_binary_artifact_missing_blob_returns_404():
    info = _ingest_binary_artifact()
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        _test_blob_store.delete(art.blob_path)
    finally:
        session.close()

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}/content")
    assert resp.status_code == 404
    assert "blob" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Timeline refs include mime_type
# ---------------------------------------------------------------------------


def test_timeline_ref_includes_mime_type_for_binary():
    info = _ingest_binary_artifact()
    assert info["status_code"] == 201

    resp = client.get(f"/v1/runs/{info['run_id']}/timeline")
    assert resp.status_code == 200

    step = resp.json()["steps"][0]
    assert len(step["artifacts"]) == 1

    ref = step["artifacts"][0]
    assert ref["mime_type"] == "image/png"
    assert ref["filename"] == "test.png"
    assert ref["storage_kind"] == "blob"
    assert ref["size_bytes"] == len(_PNG_BYTES)
    assert ref["sha256"] is not None
    assert ref["kind"] == "user_upload"


def test_timeline_ref_includes_mime_type_for_json():
    info = _ingest_json_artifact()

    resp = client.get(f"/v1/runs/{info['run_id']}/timeline")
    assert resp.status_code == 200

    ref = resp.json()["steps"][0]["artifacts"][0]
    assert ref["mime_type"] == "application/json"
    assert ref["filename"] is None
    assert ref["storage_kind"] == "inline"


# ---------------------------------------------------------------------------
# Artifact response includes mime_type
# ---------------------------------------------------------------------------


def test_artifact_response_includes_mime_type():
    info = _ingest_json_artifact()

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 200
    assert resp.json()["mime_type"] == "application/json"


# ---------------------------------------------------------------------------
# Blob key uses correct extension for binary artifacts
# ---------------------------------------------------------------------------


def test_blob_key_uses_mime_extension():
    info = _ingest_binary_artifact(mime_type="image/png")
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.blob_path.endswith(".png")
    finally:
        session.close()


def test_blob_key_uses_bin_for_unknown_mime():
    info = _ingest_binary_artifact(mime_type="application/x-custom-thing")
    assert info["status_code"] == 201

    session: Session = next(get_session())
    try:
        art = session.execute(
            select(Artifact).where(Artifact.id == info["artifact_id"])
        ).scalar_one()
        assert art.blob_path.endswith(".bin")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# preview_text preserved for binary artifacts
# ---------------------------------------------------------------------------


def test_preview_text_preserved_for_binary():
    info = _ingest_binary_artifact(preview_text="my screenshot")
    assert info["status_code"] == 201

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.json()["preview_text"] == "my screenshot"
