"""Tests for the tool_step helper — first-class tool execution tracing."""

from __future__ import annotations

import pytest

from leer.context import get_current_run, set_current_run
from leer.models import TraceRun
from leer.tool import tool_step


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _traced(fn):
    """Run ``fn`` inside a fake trace and return the run."""
    run = TraceRun(workflow_name="test-tool")
    run.status = "running"
    set_current_run(run)
    try:
        fn(run)
    finally:
        set_current_run(None)
    return run


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

class TestToolStepSuccess:

    def test_creates_tool_step(self):
        def go(run):
            with tool_step("get_weather") as s:
                s.input = {"city": "Paris"}
                s.output = {"temp": 18}

        run = _traced(go)

        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.step_type == "tool"
        assert s.name == "get_weather"
        assert s.status == "completed"

    def test_step_has_timing(self):
        def go(run):
            with tool_step("fetch") as s:
                s.output = "ok"

        run = _traced(go)
        s = run.steps[0]
        assert s.started_at is not None
        assert s.ended_at is not None
        assert s.ended_at >= s.started_at

    def test_input_summary_from_input(self):
        def go(run):
            with tool_step("search") as s:
                s.input = {"query": "restaurants"}
                s.output = {"count": 5}

        run = _traced(go)
        assert run.steps[0].input_summary == {"query": "restaurants"}

    def test_output_summary_from_output(self):
        def go(run):
            with tool_step("search") as s:
                s.input = {"q": "test"}
                s.output = {"count": 5}

        run = _traced(go)
        assert run.steps[0].output_summary == {"count": 5}

    def test_explicit_summary_not_overwritten(self):
        def go(run):
            with tool_step("calc") as s:
                s.input = {"a": 1, "b": 2}
                s.output = {"result": 3}
                s.input_summary = {"custom": True}
                s.output_summary = {"custom_out": True}

        run = _traced(go)
        assert run.steps[0].input_summary == {"custom": True}
        assert run.steps[0].output_summary == {"custom_out": True}


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class TestToolStepMetadata:

    def test_tool_name_in_metadata(self):
        def go(run):
            with tool_step("get_weather"):
                pass

        run = _traced(go)
        assert run.steps[0].metadata["tool_name"] == "get_weather"

    def test_tool_call_id_in_metadata(self):
        def go(run):
            with tool_step("get_weather", tool_call_id="call_123"):
                pass

        run = _traced(go)
        assert run.steps[0].metadata["tool_call_id"] == "call_123"

    def test_provider_and_model(self):
        def go(run):
            with tool_step(
                "get_weather",
                source_provider="openai",
                source_model="gpt-4.1",
            ):
                pass

        run = _traced(go)
        meta = run.steps[0].metadata
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4.1"

    def test_optional_fields_absent_when_not_set(self):
        def go(run):
            with tool_step("simple"):
                pass

        run = _traced(go)
        meta = run.steps[0].metadata
        assert "tool_call_id" not in meta
        assert "provider" not in meta
        assert "model" not in meta

    def test_extra_metadata_merged(self):
        def go(run):
            with tool_step("get_weather", metadata={"custom": "value"}):
                pass

        run = _traced(go)
        meta = run.steps[0].metadata
        assert meta["tool_name"] == "get_weather"
        assert meta["custom"] == "value"


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

class TestToolStepArtifacts:

    def test_request_artifact_created(self):
        def go(run):
            with tool_step("get_weather") as s:
                s.input = {"city": "Paris"}
                s.output = {"temp": 18}

        run = _traced(go)
        req = [a for a in run.artifacts if a.artifact_type == "tool_request"]
        assert len(req) == 1
        assert req[0].role == "input"
        assert req[0].inline_data == {"city": "Paris"}
        assert req[0].step_id == run.steps[0].id

    def test_response_artifact_created(self):
        def go(run):
            with tool_step("get_weather") as s:
                s.input = {"city": "Paris"}
                s.output = {"temp": 18}

        run = _traced(go)
        resp = [a for a in run.artifacts if a.artifact_type == "tool_response"]
        assert len(resp) == 1
        assert resp[0].role == "output"
        assert resp[0].inline_data == {"temp": 18}

    def test_no_artifacts_without_input_output(self):
        def go(run):
            with tool_step("noop"):
                pass

        run = _traced(go)
        assert len(run.artifacts) == 0

    def test_only_request_when_no_output(self):
        def go(run):
            with tool_step("partial") as s:
                s.input = {"q": "test"}

        run = _traced(go)
        assert len(run.artifacts) == 1
        assert run.artifacts[0].artifact_type == "tool_request"

    def test_artifact_preview_text(self):
        def go(run):
            with tool_step("get_weather") as s:
                s.input = {"city": "Paris"}
                s.output = {"temp": 18, "condition": "sunny"}

        run = _traced(go)
        req = run.artifacts[0]
        resp = run.artifacts[1]
        assert '"city": "Paris"' in req.preview_text
        assert '"temp": 18' in resp.preview_text

    def test_artifact_sequence_ordering(self):
        def go(run):
            with tool_step("tool_a") as s:
                s.input = {"a": 1}
                s.output = {"b": 2}
            with tool_step("tool_b") as s:
                s.input = {"c": 3}
                s.output = {"d": 4}

        run = _traced(go)
        indices = [a.sequence_index for a in run.artifacts]
        assert indices == [0, 1, 2, 3]

    def test_artifacts_linked_to_correct_step(self):
        def go(run):
            with tool_step("tool_a") as s:
                s.input = {"a": 1}
                s.output = {"b": 2}
            with tool_step("tool_b") as s:
                s.input = {"c": 3}
                s.output = {"d": 4}

        run = _traced(go)
        step_a_id = run.steps[0].id
        step_b_id = run.steps[1].id

        assert run.artifacts[0].step_id == step_a_id
        assert run.artifacts[1].step_id == step_a_id
        assert run.artifacts[2].step_id == step_b_id
        assert run.artifacts[3].step_id == step_b_id


# ---------------------------------------------------------------------------
# Error / failure path
# ---------------------------------------------------------------------------

class TestToolStepFailure:

    def test_exception_propagates(self):
        def go(run):
            with tool_step("boom") as s:
                s.input = {"x": 1}
                raise ValueError("tool broke")

        with pytest.raises(ValueError, match="tool broke"):
            _traced(go)

    def test_step_marked_failed(self):
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("boom"):
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        finally:
            set_current_run(None)

        assert run.steps[0].status == "failed"

    def test_error_summary_populated(self):
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("boom"):
                raise TypeError("bad type")
        except TypeError:
            pass
        finally:
            set_current_run(None)

        err = run.steps[0].error_summary
        assert err["error_type"] == "TypeError"
        assert err["message"] == "bad type"
        assert "TypeError" in err["traceback"]

    def test_error_artifact_created(self):
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("boom"):
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        finally:
            set_current_run(None)

        err_arts = [a for a in run.artifacts if a.artifact_type == "tool_error"]
        assert len(err_arts) == 1
        assert err_arts[0].role == "error"
        assert "RuntimeError" in err_arts[0].preview_text

    def test_request_artifact_on_failure_when_input_set(self):
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("boom") as s:
                s.input = {"query": "test"}
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        finally:
            set_current_run(None)

        types = [a.artifact_type for a in run.artifacts]
        assert "tool_request" in types
        assert "tool_error" in types
        assert "tool_response" not in types

    def test_failed_step_events(self):
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("boom"):
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        finally:
            set_current_run(None)

        event_types = [e.event_type for e in run.events]
        assert "step.created" in event_types
        assert "step.started" in event_types
        assert "step.failed" in event_types
        assert "step.completed" not in event_types


# ---------------------------------------------------------------------------
# Outside trace
# ---------------------------------------------------------------------------

class TestToolStepOutsideTrace:

    def test_safe_outside_trace(self):
        with tool_step("safe") as s:
            s.input = {"x": 1}
            s.output = {"y": 2}

        assert get_current_run() is None

    def test_exception_propagates_outside_trace(self):
        with pytest.raises(ValueError, match="outside"):
            with tool_step("fail"):
                raise ValueError("outside")


# ---------------------------------------------------------------------------
# Multiple tool steps
# ---------------------------------------------------------------------------

class TestMultipleToolSteps:

    def test_multiple_steps_in_one_run(self):
        def go(run):
            with tool_step("tool_a") as s:
                s.input = {"a": 1}
                s.output = {"result_a": 10}
            with tool_step("tool_b") as s:
                s.input = {"b": 2}
                s.output = {"result_b": 20}
            with tool_step("tool_c") as s:
                s.input = {"c": 3}
                s.output = {"result_c": 30}

        run = _traced(go)

        assert len(run.steps) == 3
        assert [s.name for s in run.steps] == ["tool_a", "tool_b", "tool_c"]
        assert all(s.step_type == "tool" for s in run.steps)
        assert all(s.status == "completed" for s in run.steps)
        assert len(run.artifacts) == 6

    def test_sequence_indexes_correct(self):
        def go(run):
            with tool_step("tool_a") as s:
                s.input = {"a": 1}
                s.output = {"r": 1}
            with tool_step("tool_b") as s:
                s.input = {"b": 2}
                s.output = {"r": 2}

        run = _traced(go)

        assert run.steps[0].sequence_index == 0
        assert run.steps[1].sequence_index == 1


# ---------------------------------------------------------------------------
# Step lifecycle events
# ---------------------------------------------------------------------------

class TestToolStepEvents:

    def test_success_events(self):
        def go(run):
            with tool_step("fetch") as s:
                s.output = "ok"

        run = _traced(go)

        event_types = [e.event_type for e in run.events]
        assert "step.created" in event_types
        assert "step.started" in event_types
        assert "step.completed" in event_types


# ---------------------------------------------------------------------------
# duration_ms
# ---------------------------------------------------------------------------

class TestToolStepDuration:

    def test_duration_ms_computed_on_success(self):
        def go(run):
            with tool_step("fetch") as s:
                s.output = "ok"

        run = _traced(go)
        assert run.steps[0].duration_ms is not None
        assert run.steps[0].duration_ms >= 0

    def test_duration_ms_computed_on_failure(self):
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("boom"):
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        finally:
            set_current_run(None)

        assert run.steps[0].duration_ms is not None
        assert run.steps[0].duration_ms >= 0


# ---------------------------------------------------------------------------
# Explicit step_id on artifacts
# ---------------------------------------------------------------------------

class TestExplicitStepId:

    def test_all_artifacts_have_explicit_step_id(self):
        def go(run):
            with tool_step("fetch") as s:
                s.input = {"q": "test"}
                s.output = {"result": "ok"}

        run = _traced(go)
        step_id = run.steps[0].id
        for artifact in run.artifacts:
            assert artifact.step_id == step_id

    def test_error_artifact_has_explicit_step_id(self):
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("boom") as s:
                s.input = {"x": 1}
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        finally:
            set_current_run(None)

        step_id = run.steps[0].id
        for artifact in run.artifacts:
            assert artifact.step_id == step_id


# ---------------------------------------------------------------------------
# Double artifact prevention
# ---------------------------------------------------------------------------

class TestDoubleArtifactPrevention:

    def test_no_duplicate_request_artifact(self):
        from leer.artifacts import attach_artifact, create_json_artifact

        def go(run):
            with tool_step("fetch") as s:
                s.input = {"q": "test"}
                s.output = {"r": "ok"}
                attach_artifact(create_json_artifact(
                    artifact_type="tool_request",
                    role="input",
                    data={"q": "test"},
                    step_id=s.id,
                ))

        run = _traced(go)
        requests = [a for a in run.artifacts if a.artifact_type == "tool_request"]
        assert len(requests) == 1

    def test_no_duplicate_response_artifact(self):
        from leer.artifacts import attach_artifact, create_json_artifact

        def go(run):
            with tool_step("fetch") as s:
                s.input = {"q": "test"}
                s.output = {"r": "ok"}
                attach_artifact(create_json_artifact(
                    artifact_type="tool_response",
                    role="output",
                    data={"r": "ok"},
                    step_id=s.id,
                ))

        run = _traced(go)
        responses = [a for a in run.artifacts if a.artifact_type == "tool_response"]
        assert len(responses) == 1

    def test_auto_artifacts_still_created_without_manual(self):
        def go(run):
            with tool_step("fetch") as s:
                s.input = {"q": "test"}
                s.output = {"r": "ok"}

        run = _traced(go)
        types = [a.artifact_type for a in run.artifacts]
        assert types.count("tool_request") == 1
        assert types.count("tool_response") == 1


# ---------------------------------------------------------------------------
# Preview text quality
# ---------------------------------------------------------------------------

class TestPreviewText:

    def test_nested_structure_readable(self):
        def go(run):
            with tool_step("search") as s:
                s.input = {"query": {"city": "Paris", "units": "celsius"}}
                s.output = {"results": [{"name": "Eiffel Tower"}]}

        run = _traced(go)
        req = run.artifacts[0]
        assert '"query"' in req.preview_text
        assert '"city"' in req.preview_text
