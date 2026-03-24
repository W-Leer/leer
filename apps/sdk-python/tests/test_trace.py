from unittest.mock import patch

from leer import configure, trace, step
from leer.client import _build_payload
from leer.models import TraceRun


def test_trace_produces_valid_payload():
    configure(api_base_url="http://localhost:8000", project_slug="test-project")

    captured: list[TraceRun] = []

    def mock_submit(run: TraceRun) -> None:
        captured.append(run)

    with patch("leer.decorators.submit", mock_submit):

        @trace(workflow_name="test-agent")
        def my_workflow():
            with step("prepare", step_type="code"):
                pass
            with step("llm_call", step_type="llm"):
                pass
            return "done"

        result = my_workflow()

    assert result == "done"
    assert len(captured) == 1

    run = captured[0]
    assert run.workflow_name == "test-agent"
    assert run.status == "completed"
    assert run.started_at is not None
    assert run.ended_at is not None
    assert len(run.steps) == 2
    assert run.steps[0].name == "prepare"
    assert run.steps[0].step_type == "code"
    assert run.steps[0].status == "completed"
    assert run.steps[1].name == "llm_call"
    assert run.steps[1].step_type == "llm"
    assert run.steps[1].sequence_index == 1

    event_types = [e.event_type for e in run.events]
    assert event_types == [
        "run.created",
        "run.started",
        "step.created",
        "step.started",
        "step.completed",
        "step.created",
        "step.started",
        "step.completed",
        "run.completed",
    ]


def test_payload_serialization_shape():
    configure(api_base_url="http://localhost:8000", project_slug="test-project")

    captured: list[TraceRun] = []

    with patch("leer.decorators.submit", lambda r: captured.append(r)):

        @trace(workflow_name="shape-test")
        def workflow():
            with step("s1"):
                pass
            return "ok"

        workflow()

    payload = _build_payload(captured[0])

    assert payload["project_slug"] == "test-project"
    assert "id" in payload["run"]
    assert payload["run"]["workflow_name"] == "shape-test"
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["trigger_type"] == "manual"
    assert payload["run"]["source"] == "sdk-python"
    assert isinstance(payload["run"]["started_at"], str)
    assert isinstance(payload["steps"], list)
    assert isinstance(payload["events"], list)
    assert payload["replay"] is None
