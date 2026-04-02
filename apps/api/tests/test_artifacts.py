"""Tests for the artifact content fetch endpoint and blob-aware artifact refs."""

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_session
from app.dependencies import get_blob_store
from app.main import app

from tests.conftest import shared_blob_store


# ---------------------------------------------------------------------------
# Test fixtures — session rollback + shared blob store
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


def _ingest_run_with_inline_artifact(
    *,
    artifact_type: str = "llm_request",
    inline_data: dict | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
) -> dict:
    """Ingest a run with one inline artifact via the API."""
    slug = f"art-{uuid.uuid4().hex[:8]}"
    run_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    art_id = str(uuid.uuid4())

    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "artifact-test",
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
                "role": "input",
                "format": "json",
                "storage_kind": "inline",
                "sequence_index": 0,
                "mime_type": "application/json",
                "inline_data": inline_data or {"model": "gpt-4.1"},
                "preview_text": "test preview",
                "metadata": {},
            }
        ],
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201
    return {"artifact_id": art_id, "run_id": run_id, "step_id": step_id}


def _insert_blob_artifact_directly(
    session: Session,
    *,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    step_id: uuid.UUID,
    artifact_id: uuid.UUID | None = None,
    blob_path: str = "test/blob.json",
    artifact_type: str = "llm_stream",
    preview_text: str = "blob preview",
    size_bytes: int | None = None,
    sha256: str | None = None,
) -> uuid.UUID:
    """Insert a blob artifact directly via raw SQL to bypass psycopg3 JSONB null handling."""
    art_id = artifact_id or uuid.uuid4()
    session.execute(text("""
        INSERT INTO artifacts (
            id, project_id, run_id, step_id,
            artifact_type, role, format, storage_kind, sequence_index,
            mime_type, size_bytes, inline_data, blob_path,
            preview_text, sha256, metadata
        ) VALUES (
            :id, :project_id, :run_id, :step_id,
            :artifact_type, 'output', 'json', 'blob', 0,
            'application/json', :size_bytes, NULL, :blob_path,
            :preview_text, :sha256, '{}'::jsonb
        )
    """), {
        "id": art_id,
        "project_id": project_id,
        "run_id": run_id,
        "step_id": step_id,
        "artifact_type": artifact_type,
        "blob_path": blob_path,
        "preview_text": preview_text,
        "size_bytes": size_bytes,
        "sha256": sha256,
    })
    session.flush()
    return art_id


def _setup_run_with_blob_artifact(
    *,
    blob_key: str,
    blob_data: dict,
    artifact_type: str = "llm_stream",
    size_bytes: int | None = None,
    sha256: str | None = None,
) -> dict:
    """Ingest a run, then insert a blob artifact directly for it."""
    slug = f"blob-{uuid.uuid4().hex[:8]}"
    run_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())

    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "blob-test",
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
                "name": "llm_call",
                "step_type": "llm",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00Z",
                "ended_at": "2026-03-24T12:00:01Z",
                "metadata": {},
            }
        ],
        "events": [],
        "artifacts": [],
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201

    raw = json.dumps(blob_data).encode()
    _test_blob_store.put(blob_key, raw)

    session: Session = next(get_session())
    try:
        from app.models import Project
        from sqlalchemy import select
        project = session.execute(
            select(Project).where(Project.slug == slug)
        ).scalar_one()

        art_id = _insert_blob_artifact_directly(
            session,
            project_id=project.id,
            run_id=uuid.UUID(run_id),
            step_id=uuid.UUID(step_id),
            blob_path=blob_key,
            artifact_type=artifact_type,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        session.commit()
        return {"artifact_id": str(art_id), "run_id": run_id, "step_id": step_id}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Fetch inline artifact
# ---------------------------------------------------------------------------


def test_fetch_inline_artifact():
    inline_payload = {"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]}
    info = _ingest_run_with_inline_artifact(inline_data=inline_payload)

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["id"] == info["artifact_id"]
    assert body["artifact_type"] == "llm_request"
    assert body["storage_kind"] == "inline"
    assert body["preview_text"] == "test preview"
    assert body["data"] == inline_payload


# ---------------------------------------------------------------------------
# Fetch blob-backed artifact
# ---------------------------------------------------------------------------


def test_fetch_blob_artifact():
    blob_key = f"test/{uuid.uuid4().hex}.json"
    blob_payload = {"events": [{"type": "text_delta", "text": "hello"}]}

    info = _setup_run_with_blob_artifact(
        blob_key=blob_key,
        blob_data=blob_payload,
    )

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["id"] == info["artifact_id"]
    assert body["artifact_type"] == "llm_stream"
    assert body["storage_kind"] == "blob"
    assert body["data"] == blob_payload


# ---------------------------------------------------------------------------
# Missing artifact id → 404
# ---------------------------------------------------------------------------


def test_fetch_missing_artifact_returns_404():
    resp = client.get(f"/v1/artifacts/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Blob-backed artifact whose blob object is missing → 404
# ---------------------------------------------------------------------------


def test_fetch_blob_artifact_missing_blob_returns_404():
    info = _setup_run_with_blob_artifact(
        blob_key="nonexistent/will-not-write.json",
        blob_data={},
    )
    _test_blob_store.delete("nonexistent/will-not-write.json")

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 404
    assert "blob" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Timeline refs include new blob-awareness fields
# ---------------------------------------------------------------------------


def test_timeline_artifact_ref_includes_storage_fields():
    inline_payload = {"model": "gpt-4.1"}
    info = _ingest_run_with_inline_artifact(inline_data=inline_payload)

    resp = client.get(f"/v1/runs/{info['run_id']}/timeline")
    assert resp.status_code == 200

    body = resp.json()
    step = body["steps"][0]
    assert len(step["artifacts"]) == 1

    ref = step["artifacts"][0]
    assert ref["storage_kind"] == "inline"
    assert ref["kind"] == "llm_request"
    assert "size_bytes" in ref
    assert "sha256" in ref


def test_timeline_blob_artifact_ref_shows_blob_storage_kind():
    blob_key = f"test/{uuid.uuid4().hex}.json"

    info = _setup_run_with_blob_artifact(
        blob_key=blob_key,
        blob_data={"events": []},
        size_bytes=42,
        sha256="abc123",
    )

    resp = client.get(f"/v1/runs/{info['run_id']}/timeline")
    assert resp.status_code == 200

    step = resp.json()["steps"][0]
    assert len(step["artifacts"]) == 1

    ref = step["artifacts"][0]
    assert ref["storage_kind"] == "blob"
    assert ref["kind"] == "llm_stream"
    assert ref["size_bytes"] == 42
    assert ref["sha256"] == "abc123"


# ---------------------------------------------------------------------------
# Fetch endpoint returns size_bytes and sha256
# ---------------------------------------------------------------------------


def test_fetch_artifact_returns_size_and_sha256():
    blob_key = f"test/{uuid.uuid4().hex}.json"
    info = _setup_run_with_blob_artifact(
        blob_key=blob_key,
        blob_data={"ok": True},
        size_bytes=1024,
        sha256="deadbeef",
    )

    resp = client.get(f"/v1/artifacts/{info['artifact_id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["size_bytes"] == 1024
    assert body["sha256"] == "deadbeef"
