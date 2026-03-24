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


def _ingest(slug: str, *, run_status: str = "completed", steps: list[dict] | None = None) -> dict:
    run_id = str(uuid.uuid4())
    if steps is None:
        steps = [
            {
                "id": str(uuid.uuid4()),
                "sequence_index": 0,
                "name": "step_a",
                "step_type": "code",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00Z",
                "ended_at": "2026-03-24T12:00:01Z",
                "output_summary": {"result": "hello"},
                "metadata": {},
            },
        ]
    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "cmp-workflow",
            "status": run_status,
            "trigger_type": "manual",
            "source": "sdk-python",
            "started_at": "2026-03-24T12:00:00Z",
            "ended_at": "2026-03-24T12:00:01Z",
            "metadata": {},
        },
        "steps": steps,
        "events": [],
        "artifacts": [],
        "replay": None,
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201
    return payload


def test_compare_identical_runs():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug)
    b = _ingest(slug)

    resp = client.get(f"/v1/runs/{a['run']['id']}/compare/{b['run']['id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["run_a"]["id"] == a["run"]["id"]
    assert body["run_b"]["id"] == b["run"]["id"]

    assert len(body["steps"]) == 1
    step = body["steps"][0]
    assert step["exists_in_a"] is True
    assert step["exists_in_b"] is True
    assert step["status_diff"] is False
    assert step["output_diff"] is False
    assert step["error_diff"] is False


def test_compare_changed_status_and_output():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    steps_a = [{
        "id": str(uuid.uuid4()),
        "sequence_index": 0,
        "name": "step_a",
        "step_type": "llm",
        "status": "completed",
        "started_at": "2026-03-24T12:00:00Z",
        "ended_at": "2026-03-24T12:00:01Z",
        "output_summary": {"text": "good result"},
        "metadata": {},
    }]
    steps_b = [{
        "id": str(uuid.uuid4()),
        "sequence_index": 0,
        "name": "step_a",
        "step_type": "llm",
        "status": "failed",
        "started_at": "2026-03-24T12:00:00Z",
        "ended_at": "2026-03-24T12:00:01Z",
        "error_summary": {"message": "timeout"},
        "metadata": {},
    }]

    a = _ingest(slug, steps=steps_a)
    b = _ingest(slug, run_status="failed", steps=steps_b)

    resp = client.get(f"/v1/runs/{a['run']['id']}/compare/{b['run']['id']}")
    assert resp.status_code == 200

    step = resp.json()["steps"][0]
    assert step["status_a"] == "completed"
    assert step["status_b"] == "failed"
    assert step["status_diff"] is True
    assert step["output_diff"] is True
    assert step["error_diff"] is True
    assert step["error_summary_b"] == {"message": "timeout"}


def test_compare_missing_step_on_one_side():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    steps_a = [
        {
            "id": str(uuid.uuid4()),
            "sequence_index": 0,
            "name": "step_a",
            "step_type": "code",
            "status": "completed",
            "started_at": "2026-03-24T12:00:00Z",
            "ended_at": "2026-03-24T12:00:01Z",
            "metadata": {},
        },
        {
            "id": str(uuid.uuid4()),
            "sequence_index": 1,
            "name": "step_b",
            "step_type": "llm",
            "status": "completed",
            "started_at": "2026-03-24T12:00:01Z",
            "ended_at": "2026-03-24T12:00:02Z",
            "metadata": {},
        },
    ]
    steps_b = [
        {
            "id": str(uuid.uuid4()),
            "sequence_index": 0,
            "name": "step_a",
            "step_type": "code",
            "status": "completed",
            "started_at": "2026-03-24T12:00:00Z",
            "ended_at": "2026-03-24T12:00:01Z",
            "metadata": {},
        },
    ]

    a = _ingest(slug, steps=steps_a)
    b = _ingest(slug, steps=steps_b)

    resp = client.get(f"/v1/runs/{a['run']['id']}/compare/{b['run']['id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["steps"]) == 2

    shared = body["steps"][0]
    assert shared["exists_in_a"] is True
    assert shared["exists_in_b"] is True
    assert shared["status_diff"] is False

    missing = body["steps"][1]
    assert missing["exists_in_a"] is True
    assert missing["exists_in_b"] is False
    assert missing["name_a"] == "step_b"
    assert missing["name_b"] is None
    assert missing["status_diff"] is True
