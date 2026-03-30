import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.models import Artifact, Event, Project, Run, Step

_test_slug = f"test-{uuid.uuid4().hex[:8]}"


def _make_payload() -> dict:
    run_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    return {
        "project_slug": _test_slug,
        "run": {
            "id": run_id,
            "workflow_name": "test-workflow",
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
                "step_type": "code",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00Z",
                "ended_at": "2026-03-24T12:00:01Z",
                "metadata": {},
            }
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
                "event_type": "step.started",
                "sequence_index": 1,
                "timestamp": "2026-03-24T12:00:00Z",
                "payload": {},
            },
        ],
        "artifacts": [],
        "replay": None,
    }


def _session_with_rollback():
    """Yield a session that rolls back after each test."""
    session: Session = next(get_session())
    try:
        yield session
    finally:
        session.rollback()
        session.close()


app.dependency_overrides[get_session] = _session_with_rollback
client = TestClient(app)


def test_ingest_run_happy_path():
    payload = _make_payload()
    run_id = payload["run"]["id"]

    resp = client.post("/v1/ingest/runs", json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ok"
    assert body["run_id"] == run_id


def test_ingest_creates_project_and_records():
    payload = _make_payload()
    slug = f"test-{uuid.uuid4().hex[:8]}"
    payload["project_slug"] = slug

    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201

    session: Session = next(get_session())
    try:
        project = session.query(Project).filter_by(slug=slug).first()
        assert project is not None

        run = session.query(Run).filter_by(id=payload["run"]["id"]).first()
        assert run is not None
        assert run.workflow_name == "test-workflow"
        assert run.status == "completed"

        steps = session.query(Step).filter_by(run_id=run.id).all()
        assert len(steps) == 1
        assert steps[0].name == "test_step"

        events = session.query(Event).filter_by(run_id=run.id).all()
        assert len(events) == 2
    finally:
        session.close()


def test_ingest_populates_step_and_run_llm_columns():
    """When a step carries provider/model/usage metadata, ingestion promotes them to first-class columns."""
    payload = _make_payload()
    slug = f"test-{uuid.uuid4().hex[:8]}"
    payload["project_slug"] = slug

    payload["steps"][0]["step_type"] = "llm"
    payload["steps"][0]["metadata"] = {
        "provider": "openai",
        "model": "gpt-4.1",
        "latency_ms": 150,
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201

    session: Session = next(get_session())
    try:
        step = session.query(Step).filter_by(id=payload["steps"][0]["id"]).first()
        assert step is not None
        assert step.model_provider == "openai"
        assert step.model_name == "gpt-4.1"
        assert step.duration_ms is not None
        assert step.token_input == 10
        assert step.token_output == 5

        run = session.query(Run).filter_by(id=payload["run"]["id"]).first()
        assert run is not None
        assert run.model_provider == "openai"
        assert run.model_name == "gpt-4.1"
        assert run.total_tokens_input == 10
        assert run.total_tokens_output == 5
    finally:
        session.close()


def test_ingest_with_artifacts():
    payload = _make_payload()
    step_id = payload["steps"][0]["id"]
    artifact_id = str(uuid.uuid4())
    slug = f"test-{uuid.uuid4().hex[:8]}"
    payload["project_slug"] = slug

    payload["artifacts"] = [
        {
            "id": artifact_id,
            "step_id": step_id,
            "artifact_type": "llm_request",
            "role": "input",
            "format": "json",
            "storage_kind": "inline",
            "sequence_index": 0,
            "mime_type": "application/json",
            "inline_data": {
                "model": "gpt-4.1",
                "messages": [{"role": "user", "content": "hello"}],
            },
            "preview_text": "user: hello",
            "metadata": {"provider": "openai"},
        },
    ]

    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201

    session: Session = next(get_session())
    try:
        art = session.query(Artifact).filter_by(id=artifact_id).first()
        assert art is not None
        assert art.artifact_type == "llm_request"
        assert art.role == "input"
        assert art.format_ == "json"
        assert art.storage_kind == "inline"
        assert art.sequence_index == 0
        assert art.mime_type == "application/json"
        assert art.inline_data["model"] == "gpt-4.1"
        assert art.preview_text == "user: hello"
        assert art.metadata_ == {"provider": "openai"}
        assert str(art.step_id) == step_id
    finally:
        session.close()
