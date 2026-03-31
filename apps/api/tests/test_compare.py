"""
Tests for run comparison — canonical spec (01-run-comparison-spec.md).

Required coverage:
  1. compare identical runs
  2. compare runs with changed status / output
  3. compare runs with missing steps
  4. same step names but shifted sequence indexes
  5. no exact-name match → fallback or missing
  6. provider-aware llm data on one or both sides
  7. fallback same-type nearest-index matching
  8. unmatched steps preserved (never silently dropped)
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _session_with_rollback():
    session: Session = next(get_session())
    try:
        yield session
    finally:
        session.rollback()
        session.close()


app.dependency_overrides[get_session] = _session_with_rollback
client = TestClient(app)


def _step(
    *,
    idx: int,
    name: str,
    stype: str = "code",
    status: str = "completed",
    output: dict | None = None,
    error: dict | None = None,
    input_summary: dict | None = None,
    meta: dict | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "sequence_index": idx,
        "name": name,
        "step_type": stype,
        "status": status,
        "started_at": "2026-03-24T12:00:00Z",
        "ended_at": "2026-03-24T12:00:01Z",
        "output_summary": output,
        "error_summary": error,
        "input_summary": input_summary,
        "metadata": meta or {},
    }


def _ingest(slug: str, *, run_status: str = "completed", steps: list[dict]) -> dict:
    run_id = str(uuid.uuid4())
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
    }
    resp = client.post("/v1/ingest/runs", json=payload)
    assert resp.status_code == 201
    return payload


def _compare(a: dict, b: dict) -> dict:
    resp = client.get(
        f"/v1/runs/{a['run']['id']}/compare/{b['run']['id']}"
    )
    assert resp.status_code == 200
    return resp.json()


def _find(steps: list[dict], **kw) -> dict | None:
    for s in steps:
        if all(s.get(k) == v for k, v in kw.items()):
            return s
    return None


# ---------------------------------------------------------------------------
# 1. Compare identical runs
# ---------------------------------------------------------------------------

def test_compare_identical_runs():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug, steps=[_step(idx=0, name="step_a", output={"r": "ok"})])
    b = _ingest(slug, steps=[_step(idx=0, name="step_a", output={"r": "ok"})])

    body = _compare(a, b)

    assert body["run_a"]["id"] == a["run"]["id"]
    assert body["run_b"]["id"] == b["run"]["id"]
    assert "total_steps" in body["run_a"]
    assert "total_duration_ms" in body["run_a"]

    assert len(body["steps"]) == 1
    s = body["steps"][0]
    assert s["match_kind"] == "exact_name"
    assert s["exists_in_a"] is True
    assert s["exists_in_b"] is True
    assert s["status_diff"] is False
    assert s["output_diff"] is False
    assert s["error_diff"] is False
    assert s["input_diff"] is False
    assert s["llm_a"] is None
    assert s["llm_b"] is None


# ---------------------------------------------------------------------------
# 2. Compare runs with changed status / output
# ---------------------------------------------------------------------------

def test_compare_changed_status_and_output():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug, steps=[
        _step(idx=0, name="call", stype="llm", output={"text": "good"}),
    ])
    b = _ingest(slug, run_status="failed", steps=[
        _step(idx=0, name="call", stype="llm", status="failed",
              error={"message": "timeout"}),
    ])

    s = _compare(a, b)["steps"][0]
    assert s["match_kind"] == "exact_name"
    assert s["status_diff"] is True
    assert s["output_diff"] is True
    assert s["error_diff"] is True
    assert s["error_summary_b"] == {"message": "timeout"}


# ---------------------------------------------------------------------------
# 3. Compare runs with missing steps
# ---------------------------------------------------------------------------

def test_compare_missing_step_on_one_side():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug, steps=[
        _step(idx=0, name="step_a"),
        _step(idx=1, name="step_b", stype="llm"),
    ])
    b = _ingest(slug, steps=[
        _step(idx=0, name="step_a"),
    ])

    body = _compare(a, b)
    assert len(body["steps"]) == 2

    matched = _find(body["steps"], match_kind="exact_name")
    assert matched is not None
    assert matched["name_a"] == "step_a"

    missing = _find(body["steps"], match_kind="missing")
    assert missing is not None
    assert missing["exists_in_a"] is True
    assert missing["exists_in_b"] is False
    assert missing["name_a"] == "step_b"
    assert missing["name_b"] is None
    assert missing["sequence_index_a"] == 1
    assert missing["sequence_index_b"] is None


# ---------------------------------------------------------------------------
# 4. Same step names but shifted sequence indexes
# ---------------------------------------------------------------------------

def test_name_match_across_shifted_indexes():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    a = _ingest(slug, steps=[
        _step(idx=0, name="prepare"),
        _step(idx=1, name="llm_call", stype="llm"),
    ])
    # Run B has an extra step inserted at index 0, shifting everything
    b = _ingest(slug, steps=[
        _step(idx=0, name="validate"),
        _step(idx=1, name="prepare"),
        _step(idx=2, name="llm_call", stype="llm"),
    ])

    body = _compare(a, b)
    by_name = {(s.get("name_a") or s.get("name_b")): s for s in body["steps"]}

    prep = by_name["prepare"]
    assert prep["match_kind"] == "exact_name"
    assert prep["sequence_index_a"] == 0
    assert prep["sequence_index_b"] == 1

    llm = by_name["llm_call"]
    assert llm["match_kind"] == "exact_name"
    assert llm["sequence_index_a"] == 1
    assert llm["sequence_index_b"] == 2

    val = by_name["validate"]
    assert val["match_kind"] == "missing"
    assert val["exists_in_a"] is False
    assert val["exists_in_b"] is True


# ---------------------------------------------------------------------------
# 5. No exact-name match → fallback or missing
# ---------------------------------------------------------------------------

def test_no_name_match_different_types_becomes_missing():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    a = _ingest(slug, steps=[_step(idx=0, name="setup", stype="code")])
    b = _ingest(slug, steps=[_step(idx=0, name="call_gpt", stype="llm")])

    body = _compare(a, b)
    assert len(body["steps"]) == 2
    kinds = {s["match_kind"] for s in body["steps"]}
    assert kinds == {"missing"}


# ---------------------------------------------------------------------------
# 6. Provider-aware LLM data on one or both sides
# ---------------------------------------------------------------------------

_LLM_A = {
    "provider": "openai", "model": "gpt-4o",
    "input": {"system": "You are helpful.", "messages": [{"role": "user", "content": "hi"}],
              "tools": [], "params": {}},
    "output": {"text": "Hello!", "tool_calls": [], "content_blocks": []},
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    "meta": {"latency_ms": 200, "finish_reason": "stop", "request_id": "req-1"},
}

_LLM_B = {**_LLM_A, "model": "gpt-4o-mini"}


def test_llm_data_both_sides():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug, steps=[
        _step(idx=0, name="call", stype="llm", meta={"llm": _LLM_A}),
    ])
    b = _ingest(slug, steps=[
        _step(idx=0, name="call", stype="llm", meta={"llm": _LLM_B}),
    ])

    s = _compare(a, b)["steps"][0]
    assert s["llm_a"] is not None
    assert s["llm_a"]["model"] == "gpt-4o"
    assert s["llm_b"]["model"] == "gpt-4o-mini"


def test_llm_data_one_side_only():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug, steps=[
        _step(idx=0, name="call", stype="llm", meta={"llm": _LLM_A}),
    ])
    b = _ingest(slug, steps=[
        _step(idx=0, name="call", stype="llm"),
    ])

    s = _compare(a, b)["steps"][0]
    assert s["llm_a"] is not None
    assert s["llm_b"] is None


# ---------------------------------------------------------------------------
# 7. Fallback same-type nearest-index matching
# ---------------------------------------------------------------------------

def test_fallback_type_index_match():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    a = _ingest(slug, steps=[_step(idx=0, name="fetch_data")])
    b = _ingest(slug, steps=[_step(idx=0, name="load_data")])

    body = _compare(a, b)
    assert len(body["steps"]) == 1
    s = body["steps"][0]
    assert s["match_kind"] == "fallback_type_index"
    assert s["name_a"] == "fetch_data"
    assert s["name_b"] == "load_data"


def test_fallback_nearest_index():
    """Among multiple unmatched B candidates with same type, pick nearest index."""
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    a = _ingest(slug, steps=[_step(idx=2, name="process_a")])
    b = _ingest(slug, steps=[
        _step(idx=0, name="process_x"),
        _step(idx=1, name="process_y"),
        _step(idx=3, name="process_z"),
    ])

    body = _compare(a, b)
    fb = _find(body["steps"], match_kind="fallback_type_index")
    assert fb is not None
    assert fb["name_a"] == "process_a"
    # index 1 and 3 are both distance 1; tie-break picks smaller index
    assert fb["name_b"] == "process_y"


# ---------------------------------------------------------------------------
# 8. Unmatched steps preserved
# ---------------------------------------------------------------------------

def test_unmatched_steps_never_dropped():
    """All steps appear in the result — none silently dropped."""
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    # a_only_1 (code) has no counterpart type in B → missing
    # a_only_2 (llm) can fallback-match b_only_1 (llm) → fallback
    # shared matches by name → exact_name
    a = _ingest(slug, steps=[
        _step(idx=0, name="a_only_1"),
        _step(idx=1, name="shared"),
        _step(idx=2, name="a_only_2", stype="llm"),
    ])
    b = _ingest(slug, steps=[
        _step(idx=0, name="shared"),
        _step(idx=1, name="b_only_1", stype="llm"),
    ])

    body = _compare(a, b)

    all_names_a = {s["name_a"] for s in body["steps"] if s["name_a"]}
    all_names_b = {s["name_b"] for s in body["steps"] if s["name_b"]}

    assert "a_only_1" in all_names_a
    assert "a_only_2" in all_names_a
    assert "shared" in all_names_a
    assert "shared" in all_names_b
    assert "b_only_1" in all_names_b

    exact = _find(body["steps"], match_kind="exact_name")
    assert exact is not None
    assert exact["name_a"] == "shared"

    fallback = _find(body["steps"], match_kind="fallback_type_index")
    assert fallback is not None
    assert fallback["name_a"] == "a_only_2"
    assert fallback["name_b"] == "b_only_1"

    missing_a = [s for s in body["steps"] if s["match_kind"] == "missing" and s["exists_in_a"]]
    assert len(missing_a) == 1
    assert missing_a[0]["name_a"] == "a_only_1"


# ---------------------------------------------------------------------------
# 9. Distant same-type steps are NOT force-matched
# ---------------------------------------------------------------------------

def test_distant_same_type_steps_not_force_matched():
    """Same step_type but far-apart indexes → missing, not fallback-matched."""
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    a = _ingest(slug, steps=[_step(idx=0, name="early_code")])
    b = _ingest(slug, steps=[_step(idx=10, name="late_code")])

    body = _compare(a, b)
    assert len(body["steps"]) == 2
    kinds = {s["match_kind"] for s in body["steps"]}
    assert kinds == {"missing"}, (
        "distant same-type steps should be missing, not fallback-matched"
    )


# ---------------------------------------------------------------------------
# Ordering: results by earliest sequence_index
# ---------------------------------------------------------------------------

def test_ordering_by_earliest_sequence_index():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    a = _ingest(slug, steps=[
        _step(idx=0, name="first"),
        _step(idx=2, name="third"),
    ])
    b = _ingest(slug, steps=[
        _step(idx=0, name="first"),
        _step(idx=1, name="second"),
        _step(idx=2, name="third"),
    ])

    body = _compare(a, b)
    names = [(s.get("name_a") or s.get("name_b")) for s in body["steps"]]
    assert names == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# Input diff
# ---------------------------------------------------------------------------

def test_input_diff_detected():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug, steps=[
        _step(idx=0, name="s", input_summary={"prompt": "hello"}),
    ])
    b = _ingest(slug, steps=[
        _step(idx=0, name="s", input_summary={"prompt": "goodbye"}),
    ])

    s = _compare(a, b)["steps"][0]
    assert s["input_diff"] is True
    assert s["input_summary_a"] == {"prompt": "hello"}
    assert s["input_summary_b"] == {"prompt": "goodbye"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# parent_step_id in compare responses
# ---------------------------------------------------------------------------

def test_compare_root_steps_have_null_parent_step_id():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"
    a = _ingest(slug, steps=[_step(idx=0, name="root")])
    b = _ingest(slug, steps=[_step(idx=0, name="root")])

    s = _compare(a, b)["steps"][0]
    assert "parent_step_id_a" in s
    assert "parent_step_id_b" in s
    assert s["parent_step_id_a"] is None
    assert s["parent_step_id_b"] is None


def _step_with_parent(
    *,
    idx: int,
    name: str,
    parent_step_id: str | None = None,
    stype: str = "tool",
    status: str = "completed",
    meta: dict | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "parent_step_id": parent_step_id,
        "sequence_index": idx,
        "name": name,
        "step_type": stype,
        "status": status,
        "started_at": "2026-03-24T12:00:00Z",
        "ended_at": "2026-03-24T12:00:01Z",
        "metadata": meta or {},
    }


def test_compare_child_steps_preserve_parent_step_id():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    parent_a = str(uuid.uuid4())
    parent_b = str(uuid.uuid4())

    a = _ingest(slug, steps=[
        {**_step(idx=0, name="llm_call", stype="llm"), "id": parent_a},
        _step_with_parent(idx=1, name="get_weather", parent_step_id=parent_a),
    ])
    b = _ingest(slug, steps=[
        {**_step(idx=0, name="llm_call", stype="llm"), "id": parent_b},
        _step_with_parent(idx=1, name="get_weather", parent_step_id=parent_b),
    ])

    body = _compare(a, b)
    tool = _find(body["steps"], name_a="get_weather")
    assert tool is not None
    assert tool["parent_step_id_a"] == parent_a
    assert tool["parent_step_id_b"] == parent_b


def test_compare_missing_step_has_one_side_parent():
    slug = f"cmp-{uuid.uuid4().hex[:8]}"

    parent_a = str(uuid.uuid4())

    a = _ingest(slug, steps=[
        {**_step(idx=0, name="llm_call", stype="llm"), "id": parent_a},
        _step_with_parent(idx=1, name="get_weather", parent_step_id=parent_a),
    ])
    b = _ingest(slug, steps=[
        _step(idx=0, name="llm_call", stype="llm"),
    ])

    body = _compare(a, b)
    missing = _find(body["steps"], match_kind="missing")
    assert missing is not None
    assert missing["parent_step_id_a"] == parent_a
    assert missing["parent_step_id_b"] is None


def test_404_when_run_missing():
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/v1/runs/{fake_id}/compare/{fake_id}")
    assert resp.status_code == 404
