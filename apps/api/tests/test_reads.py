import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app


def _session_with_rollback():
    session: Session = next(get_session())
    try:
        yield session
    finally:
        session.rollback()
        session.close()


app.dependency_overrides[get_session] = _session_with_rollback
client = TestClient(app)


def _ingest(slug: str) -> dict:
    """Ingest a run and return the payload used."""
    run_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "read-test-workflow",
            "status": "completed",
            "trigger_type": "manual",
            "source": "sdk-python",
            "started_at": "2026-03-24T12:00:00Z",
            "ended_at": "2026-03-24T12:00:01Z",
            "output_summary": {"preview": "ok"},
            "metadata": {},
        },
        "steps": [
            {
                "id": step_id,
                "sequence_index": 0,
                "name": "step_a",
                "step_type": "code",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00Z",
                "ended_at": "2026-03-24T12:00:01Z",
                "metadata": {},
            },
        ],
        "events": [
            {
                "id": str(uuid.uuid4()),
                "event_type": "run.started",
                "sequence_index": 0,
                "timestamp": "2026-03-24T12:00:00Z",
                "payload": {},
            },
            {
                "id": str(uuid.uuid4()),
                "step_id": step_id,
                "event_type": "step.completed",
                "sequence_index": 1,
                "timestamp": "2026-03-24T12:00:01Z",
                "payload": {},
            },
        ],
        "artifacts": [],
        "replay": None,
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201
    return payload


def test_list_project_runs():
    slug = f"read-{uuid.uuid4().hex[:8]}"
    payload = _ingest(slug)
    run_id = payload["run"]["id"]

    resp = client.get(f"/v1/projects/{slug}/runs")
    assert resp.status_code == 200

    body = resp.json()
    assert body["project"]["slug"] == slug
    assert len(body["runs"]) >= 1
    assert body["count"] == len(body["runs"])

    run = next(r for r in body["runs"] if r["id"] == run_id)
    assert run["workflow_name"] == "read-test-workflow"
    assert run["status"] == "completed"
    assert run["total_steps"] == 1
    assert run["completed_steps"] == 1


def test_list_project_runs_404():
    resp = client.get("/v1/projects/nonexistent-slug/runs")
    assert resp.status_code == 404


def test_get_run_detail():
    slug = f"read-{uuid.uuid4().hex[:8]}"
    payload = _ingest(slug)
    run_id = payload["run"]["id"]

    resp = client.get(f"/v1/runs/{run_id}")
    assert resp.status_code == 200

    body = resp.json()["run"]
    assert body["id"] == run_id
    assert body["workflow_name"] == "read-test-workflow"
    assert body["status"] == "completed"
    assert body["total_duration_ms"] == 1000
    assert body["output_summary"] == {"preview": "ok"}


def test_get_run_detail_404():
    resp = client.get(f"/v1/runs/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_run_timeline():
    slug = f"read-{uuid.uuid4().hex[:8]}"
    payload = _ingest(slug)
    run_id = payload["run"]["id"]

    resp = client.get(f"/v1/runs/{run_id}/timeline")
    assert resp.status_code == 200

    body = resp.json()
    assert body["run"]["id"] == run_id

    assert len(body["steps"]) == 1
    assert body["steps"][0]["name"] == "step_a"
    assert body["steps"][0]["step_type"] == "code"
    assert body["steps"][0]["status"] == "completed"

    assert len(body["events"]) == 2
    types = [e["event_type"] for e in body["events"]]
    assert "run.started" in types
    assert "step.completed" in types

    assert body["artifacts"] == []
