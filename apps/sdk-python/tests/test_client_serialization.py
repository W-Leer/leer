"""Submission payloads must never fail to serialize.

`submit()` posts the run with `httpx.post(json=payload)`, which uses plain
`json.dumps` with no fallback encoder — and wraps failure in a broad except
that *silently drops the whole run*. A non-JSON-serializable value anywhere in
the captured payload (most commonly a pydantic model *class* passed as
`response_format` / `text_format` to the OpenAI `.parse()` / `.stream()`
helpers) would therefore lose the entire run.

These tests pin a safe encoder that preserves structure and replaces only the
offending leaf.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from leer import client as client_mod
from leer.client import _build_payload, _encode_payload, _json_default
from leer.context import reset_context, set_current_run
from leer.integrations.openai import wrap_openai_client
from leer.models import TraceRun


def _traced(fn: Any) -> TraceRun:
    run = TraceRun(workflow_name="serialization")
    run.status = "running"
    set_current_run(run)
    reset_context()
    try:
        fn(run)
    finally:
        set_current_run(None)
    return run


# ---------------------------------------------------------------------------
# _json_default — fallback encoder for stray non-serializable values
# ---------------------------------------------------------------------------

class TestJsonDefault:

    def test_plain_class_becomes_readable_marker(self):
        class Schema:
            pass
        out = _json_default(Schema)
        assert isinstance(out, str)
        assert "Schema" in out

    def test_set_becomes_list(self):
        assert sorted(_json_default({3, 1, 2})) == [1, 2, 3]

    def test_bytes_become_text(self):
        assert _json_default(b"hi") == "hi"

    def test_datetime_becomes_isoformat(self):
        dt = datetime(2026, 6, 20, 1, 2, 3, tzinfo=timezone.utc)
        assert _json_default(dt) == dt.isoformat()

    def test_pydantic_like_instance_uses_model_dump(self):
        class Inst:
            def model_dump(self) -> dict[str, Any]:
                return {"a": 1}
        assert _json_default(Inst()) == {"a": 1}

    def test_pydantic_like_class_preserves_schema(self):
        class ModelCls:
            @classmethod
            def model_json_schema(cls) -> dict[str, Any]:
                return {"type": "object", "title": "ModelCls"}
        assert _json_default(ModelCls) == {"type": "object", "title": "ModelCls"}

    def test_unknown_object_never_raises(self):
        class Weird:
            __slots__ = ()
        assert isinstance(_json_default(Weird()), str)


# ---------------------------------------------------------------------------
# Payload encoding end-to-end
# ---------------------------------------------------------------------------

def _parse_chat_run() -> TraceRun:
    """A run produced by `.parse()` with a non-serializable response_format."""
    class Schema:  # stand-in for a pydantic model class
        pass

    resp = {
        "id": "p1", "model": "gpt-4.1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}", "parsed": {}},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
    }

    def go(run):
        client = MagicMock()
        client.chat.completions.parse.return_value = resp
        wrap_openai_client(client).chat.completions.parse(
            model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
            response_format=Schema,
        )
    return _traced(go)


class TestPayloadEncoding:

    def test_plain_dumps_fails_on_nonserializable_request_kwarg(self):
        """Documents the risk: today's `httpx.post(json=...)` path would raise
        (and the broad except would drop the run)."""
        payload = _build_payload(_parse_chat_run())
        with pytest.raises(TypeError):
            json.dumps(payload)

    def test_encode_payload_is_safe_and_preserves_structure(self):
        payload = _build_payload(_parse_chat_run())
        encoded = _encode_payload(payload)
        assert isinstance(encoded, (bytes, bytearray))
        decoded = json.loads(encoded)
        # The request structure survives; only the offending leaf is replaced.
        text = encoded.decode()
        assert "gpt-4.1" in text
        assert "Schema" in text
        assert decoded["run"]["workflow_name"] == "serialization"

    def test_submit_posts_safe_json_content(self):
        run = _parse_chat_run()
        original = client_mod._config.api_base_url
        try:
            client_mod.configure(api_base_url="http://test.local", project_slug="p")
            with patch.object(client_mod, "httpx") as mock_httpx:
                client_mod.submit(run)
            assert mock_httpx.post.called
            kwargs = mock_httpx.post.call_args.kwargs
            content = kwargs.get("content")
            assert content is not None, "submit must post pre-encoded content"
            # Valid JSON — does not raise.
            json.loads(content)
        finally:
            client_mod._config.api_base_url = original
