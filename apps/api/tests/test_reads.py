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
    assert body["total_count"] >= len(body["runs"])
    assert "has_more" in body

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
    s = body["steps"][0]
    assert s["name"] == "step_a"
    assert s["step_type"] == "code"
    assert s["status"] == "completed"

    assert s["llm"] is None
    assert s["artifacts"] == []
    assert s["model_provider"] is None
    assert s["model_name"] is None
    assert s["duration_ms"] is not None

    assert len(body["events"]) == 2
    types = [e["event_type"] for e in body["events"]]
    assert "run.started" in types
    assert "step.completed" in types

    assert body["artifacts"] == []


def _ingest_llm_run(slug: str) -> dict:
    """Ingest a run with an LLM step and artifacts — simulates the OpenAI wrapper output."""
    run_id = str(uuid.uuid4())
    code_step_id = str(uuid.uuid4())
    llm_step_id = str(uuid.uuid4())
    req_artifact_id = str(uuid.uuid4())
    resp_artifact_id = str(uuid.uuid4())

    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "llm-test-workflow",
            "status": "completed",
            "trigger_type": "manual",
            "source": "sdk-python",
            "started_at": "2026-03-24T12:00:00Z",
            "ended_at": "2026-03-24T12:00:02Z",
            "output_summary": {"text": "Hello from the LLM"},
            "metadata": {},
        },
        "steps": [
            {
                "id": code_step_id,
                "sequence_index": 0,
                "name": "prepare_prompt",
                "step_type": "code",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00Z",
                "ended_at": "2026-03-24T12:00:00.500Z",
                "metadata": {},
            },
            {
                "id": llm_step_id,
                "sequence_index": 1,
                "name": "gpt-4.1",
                "step_type": "llm",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00.500Z",
                "ended_at": "2026-03-24T12:00:01.800Z",
                "input_summary": {"model": "gpt-4.1", "user": "Explain AI"},
                "output_summary": {"text": "Hello from the LLM", "tokens": 43},
                "metadata": {
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "latency_ms": 1300,
                    "finish_reason": "stop",
                    "request_id": "chatcmpl-test",
                    "usage": {
                        "prompt_tokens": 25,
                        "completion_tokens": 18,
                        "total_tokens": 43,
                    },
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4.1",
                        "input": {
                            "system": "You are helpful.",
                            "messages": [{"role": "user", "content": "Explain AI"}],
                            "tools": [],
                            "params": {},
                        },
                        "output": {
                            "text": "Hello from the LLM",
                            "tool_calls": [],
                            "content_blocks": [
                                {"type": "text", "text": "Hello from the LLM"}
                            ],
                        },
                        "usage": {
                            "prompt_tokens": 25,
                            "completion_tokens": 18,
                            "total_tokens": 43,
                        },
                        "meta": {
                            "finish_reason": "stop",
                            "request_id": "chatcmpl-test",
                            "latency_ms": 1300,
                        },
                    },
                },
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
        ],
        "artifacts": [
            {
                "id": req_artifact_id,
                "step_id": llm_step_id,
                "artifact_type": "llm_request",
                "role": "input",
                "format": "json",
                "storage_kind": "inline",
                "sequence_index": 0,
                "mime_type": "application/json",
                "inline_data": {
                    "model": "gpt-4.1",
                    "messages": [{"role": "user", "content": "Explain AI"}],
                },
                "preview_text": "model: gpt-4.1 | user: Explain AI",
                "metadata": {},
            },
            {
                "id": resp_artifact_id,
                "step_id": llm_step_id,
                "artifact_type": "llm_response",
                "role": "output",
                "format": "json",
                "storage_kind": "inline",
                "sequence_index": 1,
                "mime_type": "application/json",
                "inline_data": {
                    "id": "chatcmpl-test",
                    "model": "gpt-4.1",
                    "choices": [
                        {
                            "message": {"content": "Hello from the LLM"},
                            "finish_reason": "stop",
                        }
                    ],
                },
                "preview_text": "Hello from the LLM",
                "metadata": {},
            },
        ],
        "replay": None,
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201
    return payload


def test_timeline_llm_step_has_promoted_llm_field():
    slug = f"read-{uuid.uuid4().hex[:8]}"
    payload = _ingest_llm_run(slug)
    run_id = payload["run"]["id"]

    resp = client.get(f"/v1/runs/{run_id}/timeline")
    assert resp.status_code == 200
    body = resp.json()

    code_step = body["steps"][0]
    llm_step = body["steps"][1]

    assert code_step["llm"] is None
    assert code_step["model_provider"] is None
    assert code_step["artifacts"] == []

    assert llm_step["llm"] is not None
    llm = llm_step["llm"]
    assert llm["provider"] == "openai"
    assert llm["model"] == "gpt-4.1"
    assert llm["output"]["text"] == "Hello from the LLM"
    assert llm["input"]["system"] == "You are helpful."
    assert llm["usage"]["total_tokens"] == 43
    assert llm["meta"]["finish_reason"] == "stop"

    assert llm_step["model_provider"] == "openai"
    assert llm_step["model_name"] == "gpt-4.1"
    assert llm_step["duration_ms"] is not None

    assert "llm" not in llm_step["metadata"]
    assert llm_step["metadata"]["provider"] == "openai"


def test_timeline_root_step_has_null_parent_step_id():
    slug = f"read-{uuid.uuid4().hex[:8]}"
    payload = _ingest(slug)
    run_id = payload["run"]["id"]

    resp = client.get(f"/v1/runs/{run_id}/timeline")
    assert resp.status_code == 200

    s = resp.json()["steps"][0]
    assert "parent_step_id" in s
    assert s["parent_step_id"] is None


def test_timeline_child_step_has_correct_parent_step_id():
    slug = f"read-{uuid.uuid4().hex[:8]}"
    run_id = str(uuid.uuid4())
    parent_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())

    payload = {
        "project_slug": slug,
        "run": {
            "id": run_id,
            "workflow_name": "parent-child-test",
            "status": "completed",
            "trigger_type": "manual",
            "source": "sdk-python",
            "started_at": "2026-03-24T12:00:00Z",
            "ended_at": "2026-03-24T12:00:02Z",
            "metadata": {},
        },
        "steps": [
            {
                "id": parent_id,
                "sequence_index": 0,
                "name": "llm_call",
                "step_type": "llm",
                "status": "completed",
                "started_at": "2026-03-24T12:00:00Z",
                "ended_at": "2026-03-24T12:00:01Z",
                "metadata": {},
            },
            {
                "id": child_id,
                "parent_step_id": parent_id,
                "sequence_index": 1,
                "name": "get_weather",
                "step_type": "tool",
                "status": "completed",
                "started_at": "2026-03-24T12:00:01Z",
                "ended_at": "2026-03-24T12:00:02Z",
                "metadata": {"tool_call_id": "call_123"},
            },
        ],
        "events": [],
        "artifacts": [],
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201

    resp = client.get(f"/v1/runs/{run_id}/timeline")
    assert resp.status_code == 200
    steps = resp.json()["steps"]

    parent = next(s for s in steps if s["id"] == parent_id)
    child = next(s for s in steps if s["id"] == child_id)

    assert parent["parent_step_id"] is None
    assert child["parent_step_id"] == parent_id
    assert child["sequence_index"] == 1


def test_timeline_step_artifacts_are_light():
    slug = f"read-{uuid.uuid4().hex[:8]}"
    payload = _ingest_llm_run(slug)
    run_id = payload["run"]["id"]

    resp = client.get(f"/v1/runs/{run_id}/timeline")
    body = resp.json()

    llm_step = body["steps"][1]
    assert len(llm_step["artifacts"]) == 2

    req_ref = llm_step["artifacts"][0]
    assert req_ref["kind"] == "llm_request"
    assert req_ref["role"] == "input"
    assert req_ref["format"] == "json"
    assert req_ref["preview_text"] == "model: gpt-4.1 | user: Explain AI"
    assert req_ref["sequence_index"] == 0
    assert "inline_data" not in req_ref
    assert "storage_kind" not in req_ref
    assert "artifact_type" not in req_ref

    resp_ref = llm_step["artifacts"][1]
    assert resp_ref["kind"] == "llm_response"
    assert resp_ref["role"] == "output"
    assert resp_ref["preview_text"] == "Hello from the LLM"
    assert resp_ref["sequence_index"] == 1

    assert len(body["artifacts"]) == 2
    for art in body["artifacts"]:
        assert "kind" in art
        assert "inline_data" not in art
        assert "storage_kind" not in art
