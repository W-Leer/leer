from unittest.mock import patch

from leer import (
    attach_artifact,
    configure,
    create_json_artifact,
    create_text_artifact,
    step,
    trace,
)
from leer.client import _build_payload
from leer.models import TraceRun


def test_create_json_artifact_fields():
    a = create_json_artifact(
        "llm_request",
        role="input",
        data={"messages": [{"role": "user", "content": "hi"}]},
        preview_text="user: hi",
        metadata={"provider": "openai"},
    )
    assert a.artifact_type == "llm_request"
    assert a.role == "input"
    assert a.format == "json"
    assert a.storage_kind == "inline"
    assert a.mime_type == "application/json"
    assert a.inline_data == {"messages": [{"role": "user", "content": "hi"}]}
    assert a.preview_text == "user: hi"
    assert a.metadata == {"provider": "openai"}
    assert a.blob_path is None


def test_create_json_artifact_wraps_list():
    a = create_json_artifact("tool_result", data=[1, 2, 3])
    assert a.inline_data == {"data": [1, 2, 3]}


def test_create_text_artifact_fields():
    a = create_text_artifact(
        "llm_response",
        role="output",
        text="Hello, world!",
    )
    assert a.artifact_type == "llm_response"
    assert a.role == "output"
    assert a.format == "text"
    assert a.storage_kind == "inline"
    assert a.mime_type == "text/plain"
    assert a.inline_data == {"text": "Hello, world!"}
    assert a.preview_text == "Hello, world!"


def test_create_text_artifact_truncates_preview():
    long_text = "x" * 500
    a = create_text_artifact("document", text=long_text)
    assert len(a.preview_text) == 200


def test_attach_artifact_sets_step_and_sequence():
    configure(api_base_url="http://localhost:8000", project_slug="test")
    captured: list[TraceRun] = []

    with patch("leer.decorators.submit", lambda r: captured.append(r)):

        @trace(workflow_name="artifact-test")
        def workflow():
            with step("llm_call", step_type="llm") as s:
                a1 = attach_artifact(create_json_artifact(
                    "llm_request", role="input",
                    data={"messages": []},
                ))
                a2 = attach_artifact(create_json_artifact(
                    "llm_response", role="output",
                    data={"text": "response"},
                    preview_text="response",
                ))
                assert a1.step_id == s.id
                assert a2.step_id == s.id
            return "done"

        workflow()

    run = captured[0]
    assert len(run.artifacts) == 2
    assert run.artifacts[0].sequence_index == 0
    assert run.artifacts[1].sequence_index == 1
    assert run.artifacts[0].artifact_type == "llm_request"
    assert run.artifacts[1].artifact_type == "llm_response"


def test_attach_artifact_outside_trace():
    a = create_json_artifact("llm_request", data={"messages": []})
    result = attach_artifact(a)
    assert result is a
    assert a.step_id is None
    assert a.sequence_index is None


def test_artifact_serialization_round_trip():
    configure(api_base_url="http://localhost:8000", project_slug="test")
    captured: list[TraceRun] = []

    with patch("leer.decorators.submit", lambda r: captured.append(r)):

        @trace(workflow_name="serial-test")
        def workflow():
            with step("s1", step_type="llm"):
                attach_artifact(create_json_artifact(
                    "llm_request",
                    role="input",
                    data={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
                    preview_text="user: hi",
                    metadata={"provider": "openai"},
                ))
            return "ok"

        workflow()

    payload = _build_payload(captured[0])
    arts = payload["artifacts"]
    assert len(arts) == 1

    a = arts[0]
    assert a["artifact_type"] == "llm_request"
    assert a["role"] == "input"
    assert a["format"] == "json"
    assert a["storage_kind"] == "inline"
    assert a["sequence_index"] == 0
    assert a["mime_type"] == "application/json"
    assert a["inline_data"]["model"] == "gpt-4.1"
    assert a["preview_text"] == "user: hi"
    assert a["metadata"] == {"provider": "openai"}
    assert a["blob_path"] is None
    assert a["step_id"] is not None
