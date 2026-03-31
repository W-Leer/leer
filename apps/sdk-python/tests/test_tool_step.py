"""Tests for the tool_step helper — first-class tool execution tracing."""

from __future__ import annotations

import pytest

from leer.context import get_current_run, set_current_run
from leer.models import TraceRun
from leer.step import step
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


# ---------------------------------------------------------------------------
# LLM → tool linkage (Phase 4)
# ---------------------------------------------------------------------------

class TestLLMToolLinkage:
    """Verify that tool_call_id links an LLM-emitted tool call to its
    corresponding tool execution step, and that provider/model metadata
    is preserved on tool steps for future UI/compare/replay use."""

    def test_tool_call_id_links_llm_and_tool_steps(self):
        from leer.step import step

        tool_call_id = "call_abc123"

        def go(run):
            with step("gpt-4.1", step_type="llm") as llm_s:
                llm_s.output_summary = {
                    "tool_calls": [
                        {"id": tool_call_id, "name": "get_weather", "arguments": {"city": "Paris"}}
                    ],
                }

            with tool_step(
                "get_weather",
                tool_call_id=tool_call_id,
                source_provider="openai",
                source_model="gpt-4.1",
            ) as s:
                s.input = {"city": "Paris"}
                s.output = {"temperature": 18, "condition": "sunny"}

        run = _traced(go)

        llm_step = run.steps[0]
        tool_s = run.steps[1]

        emitted_id = llm_step.output_summary["tool_calls"][0]["id"]
        linked_id = tool_s.metadata["tool_call_id"]
        assert emitted_id == linked_id == tool_call_id

    def test_provider_and_model_preserved_on_tool_step(self):
        def go(run):
            with tool_step(
                "get_weather",
                tool_call_id="call_xyz",
                source_provider="anthropic",
                source_model="claude-sonnet-4-20250514",
            ) as s:
                s.input = {"city": "London"}
                s.output = {"temp": 12}

        run = _traced(go)
        meta = run.steps[0].metadata

        assert meta["tool_call_id"] == "call_xyz"
        assert meta["provider"] == "anthropic"
        assert meta["model"] == "claude-sonnet-4-20250514"
        assert meta["tool_name"] == "get_weather"

    def test_multiple_tool_calls_linked_independently(self):
        from leer.step import step

        def go(run):
            with step("gpt-4.1", step_type="llm") as llm_s:
                llm_s.output_summary = {
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}},
                        {"id": "call_2", "name": "search_docs", "arguments": {"query": "rain"}},
                    ],
                }

            with tool_step("get_weather", tool_call_id="call_1", source_provider="openai", source_model="gpt-4.1") as s:
                s.input = {"city": "Paris"}
                s.output = {"temp": 18}

            with tool_step("search_docs", tool_call_id="call_2", source_provider="openai", source_model="gpt-4.1") as s:
                s.input = {"query": "rain"}
                s.output = {"count": 3}

        run = _traced(go)

        assert len(run.steps) == 3
        tool_1 = run.steps[1]
        tool_2 = run.steps[2]

        assert tool_1.metadata["tool_call_id"] == "call_1"
        assert tool_1.metadata["tool_name"] == "get_weather"
        assert tool_2.metadata["tool_call_id"] == "call_2"
        assert tool_2.metadata["tool_name"] == "search_docs"

    def test_linkage_survives_serialization(self):
        """Verify tool_call_id and provider/model survive the serialize path."""
        from leer.client import _serialize_step

        def go(run):
            with tool_step(
                "get_weather",
                tool_call_id="call_ser",
                source_provider="openai",
                source_model="gpt-4.1",
            ) as s:
                s.input = {"city": "Paris"}
                s.output = {"temp": 18}

        run = _traced(go)
        payload = _serialize_step(run.steps[0])

        assert payload["step_type"] == "tool"
        assert payload["name"] == "get_weather"
        assert payload["metadata"]["tool_call_id"] == "call_ser"
        assert payload["metadata"]["provider"] == "openai"
        assert payload["metadata"]["model"] == "gpt-4.1"
        assert payload["duration_ms"] is not None

    def test_tool_step_without_linkage_still_works(self):
        """A tool step with no tool_call_id or provider is still valid."""
        def go(run):
            with tool_step("manual_tool") as s:
                s.input = {"x": 1}
                s.output = {"y": 2}

        run = _traced(go)
        meta = run.steps[0].metadata

        assert meta["tool_name"] == "manual_tool"
        assert "tool_call_id" not in meta
        assert "provider" not in meta
        assert "model" not in meta
        assert run.steps[0].status == "completed"


# ---------------------------------------------------------------------------
# Parent / child step relationships
# ---------------------------------------------------------------------------

class TestParentChildSteps:
    """Verify parent_step_id is correctly resolved for tool and generic steps."""

    def test_tool_step_inside_llm_step_gets_llm_as_parent(self):
        def go(run):
            with step("gpt-call", step_type="llm") as llm:
                with tool_step("get_weather") as ts:
                    ts.output = {"temp": 20}

        run = _traced(go)

        llm_step = run.steps[0]
        tool = run.steps[1]
        assert llm_step.step_type == "llm"
        assert tool.step_type == "tool"
        assert tool.parent_step_id == llm_step.id

    def test_root_tool_step_has_null_parent(self):
        def go(run):
            with tool_step("standalone") as ts:
                ts.output = "ok"

        run = _traced(go)
        assert run.steps[0].parent_step_id is None

    def test_root_generic_step_has_null_parent(self):
        def go(run):
            with step("root-step") as s:
                s.output = "ok"

        run = _traced(go)
        assert run.steps[0].parent_step_id is None

    def test_explicit_parent_step_id_override_on_tool_step(self):
        def go(run):
            with step("orchestrator", step_type="llm") as llm:
                pass
            with tool_step("detached_tool", parent_step_id=llm.id) as ts:
                ts.output = "done"

        run = _traced(go)

        llm_step = run.steps[0]
        tool = run.steps[1]
        assert tool.parent_step_id == llm_step.id

    def test_explicit_parent_step_id_override_on_generic_step(self):
        def go(run):
            with step("parent-step") as parent:
                pass
            with step("child-step", parent_step_id=parent.id) as child:
                child.output = "done"

        run = _traced(go)

        assert run.steps[1].parent_step_id == run.steps[0].id

    def test_explicit_null_parent_overrides_context(self):
        """Passing parent_step_id=None inside a parent step creates a root step."""
        def go(run):
            with step("outer", step_type="llm"):
                with tool_step("forced_root", parent_step_id=None) as ts:
                    ts.output = "root"

        run = _traced(go)

        tool = run.steps[1]
        assert tool.parent_step_id is None

    def test_multiple_sibling_children_share_parent(self):
        def go(run):
            with step("parent-llm", step_type="llm") as llm:
                with tool_step("tool_a") as a:
                    a.output = "a"
                with tool_step("tool_b") as b:
                    b.output = "b"
                with tool_step("tool_c") as c:
                    c.output = "c"

        run = _traced(go)

        parent_id = run.steps[0].id
        assert run.steps[1].parent_step_id == parent_id
        assert run.steps[2].parent_step_id == parent_id
        assert run.steps[3].parent_step_id == parent_id

    def test_sibling_children_via_explicit_override(self):
        """Fan-out: multiple tool steps after parent exits, linked via explicit ID."""
        def go(run):
            with step("orchestrator", step_type="llm") as llm:
                pass

            for name in ["fetch_a", "fetch_b", "fetch_c"]:
                with tool_step(name, parent_step_id=llm.id) as ts:
                    ts.output = f"result_{name}"

        run = _traced(go)

        orch_id = run.steps[0].id
        assert len(run.steps) == 4
        for child in run.steps[1:]:
            assert child.parent_step_id == orch_id

    def test_children_keep_global_sequence_index(self):
        def go(run):
            with step("root-1"):
                pass
            with step("parent", step_type="llm") as parent:
                with tool_step("child_a") as a:
                    a.output = "a"
                with tool_step("child_b") as b:
                    b.output = "b"
            with step("root-2"):
                pass

        run = _traced(go)

        indices = [s.sequence_index for s in run.steps]
        assert indices == [0, 1, 2, 3, 4]

    def test_serialized_payload_preserves_parent_step_id(self):
        from leer.client import _build_payload, _serialize_step

        def go(run):
            with step("parent", step_type="llm") as llm:
                with tool_step("child_tool") as ts:
                    ts.output = "ok"

        run = _traced(go)

        payload = _build_payload(run)
        step_payloads = payload["steps"]
        assert step_payloads[0]["parent_step_id"] is None
        assert step_payloads[1]["parent_step_id"] == run.steps[0].id
