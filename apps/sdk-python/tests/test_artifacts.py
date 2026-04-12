import base64
from unittest.mock import patch

from leer import (
    attach_artifact,
    configure,
    create_binary_artifact,
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


# ---------------------------------------------------------------------------
# Binary / media artifact helpers
# ---------------------------------------------------------------------------

_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def test_create_binary_artifact_fields():
    a = create_binary_artifact(
        "user_upload",
        data=_PNG_HEADER,
        mime_type="image/png",
        role="input",
        filename="screenshot.png",
        preview_text="user screenshot",
        metadata={"source": "paste"},
    )
    assert a.artifact_type == "user_upload"
    assert a.role == "input"
    assert a.format == "binary"
    assert a.storage_kind == "blob"
    assert a.mime_type == "image/png"
    assert a.binary_data == _PNG_HEADER
    assert a.inline_data is None
    assert a.preview_text == "user screenshot"
    assert a.filename == "screenshot.png"
    assert a.metadata == {"source": "paste"}


def test_create_binary_artifact_minimal():
    a = create_binary_artifact("media", data=b"\xff\xd8\xff", mime_type="image/jpeg")
    assert a.artifact_type == "media"
    assert a.role is None
    assert a.format == "binary"
    assert a.storage_kind == "blob"
    assert a.mime_type == "image/jpeg"
    assert a.binary_data == b"\xff\xd8\xff"
    assert a.metadata == {}


def test_binary_artifact_serialization():
    raw = b"hello world binary"
    a = create_binary_artifact("doc", data=raw, mime_type="application/pdf", role="output")

    from leer.client import _serialize_artifact
    d = _serialize_artifact(a)
    assert d["artifact_type"] == "doc"
    assert d["storage_kind"] == "blob"
    assert d["format"] == "binary"
    assert d["mime_type"] == "application/pdf"
    assert d["inline_data"] is None
    assert "binary_data_b64" in d
    assert base64.b64decode(d["binary_data_b64"]) == raw


def test_json_artifact_has_no_binary_data_b64():
    a = create_json_artifact("llm_request", data={"model": "gpt-4.1"})
    from leer.client import _serialize_artifact
    d = _serialize_artifact(a)
    assert "binary_data_b64" not in d


def test_binary_artifact_round_trip_in_payload():
    configure(api_base_url="http://localhost:8000", project_slug="test")
    captured: list[TraceRun] = []
    raw = b"\x89PNG" + b"\x00" * 50

    with patch("leer.decorators.submit", lambda r: captured.append(r)):

        @trace(workflow_name="binary-test")
        def workflow():
            with step("upload", step_type="tool"):
                attach_artifact(create_binary_artifact(
                    "user_image",
                    data=raw,
                    mime_type="image/png",
                    role="input",
                    filename="test.png",
                ))
            return "ok"

        workflow()

    payload = _build_payload(captured[0])
    arts = payload["artifacts"]
    assert len(arts) == 1

    a = arts[0]
    assert a["storage_kind"] == "blob"
    assert a["format"] == "binary"
    assert a["mime_type"] == "image/png"
    assert a["inline_data"] is None
    assert base64.b64decode(a["binary_data_b64"]) == raw
    assert a["filename"] == "test.png"
