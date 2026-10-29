"""OpenAI Responses output items added or changed since June 2026.

Covers drift-assessment gaps D-H2 (custom tool calls), D-H3 (message
``phase``) and D-M1 (function-call ``namespace``). See
``docs/04-execution/provider-drift-assessment-2026-10.md``.
"""

from __future__ import annotations

from typing import Any

from leer.integrations.normalize import normalize_openai


def _normalize(output: list[dict[str, Any]]) -> dict[str, Any]:
    response = {"id": "resp_1", "model": "gpt-5.5", "status": "completed", "output": output, "usage": {}}
    return normalize_openai({"model": "gpt-5.5", "input": "x"}, response).to_dict()


def _message(text: str, phase: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "type": "message", "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }
    if phase is not None:
        msg["phase"] = phase
    return msg


# ---------------------------------------------------------------------------
# D-H3 — phase
# ---------------------------------------------------------------------------

class TestMessagePhase:

    def test_commentary_is_excluded_from_output_text(self) -> None:
        d = _normalize([_message("Let me check.", "commentary"), _message("Done.", "final_answer")])
        assert d["output"]["text"] == "Done."

    def test_commentary_is_kept_as_a_tagged_content_block(self) -> None:
        d = _normalize([_message("Let me check.", "commentary"), _message("Done.", "final_answer")])
        blocks = [b for b in d["output"]["content_blocks"] if b["type"] == "text"]
        assert blocks == [
            {"type": "text", "text": "Let me check.", "phase": "commentary"},
            {"type": "text", "text": "Done.", "phase": "final_answer"},
        ]

    def test_structured_detection_uses_the_final_answer(self) -> None:
        d = _normalize([_message("Working on it.", "commentary"), _message('{"answer": 42}', "final_answer")])
        assert d["meta"]["output_is_json"] is True
        assert d["output"]["parsed"] == {"answer": 42}

    def test_commentary_only_still_produces_text(self) -> None:
        """A response cut short after commentary must not lose its only text."""
        d = _normalize([_message("Let me check.", "commentary")])
        assert d["output"]["text"] == "Let me check."

    def test_messages_without_phase_are_unchanged(self) -> None:
        d = _normalize([_message("Hello"), _message("World")])
        assert d["output"]["text"] == "Hello\n\nWorld"
        assert all("phase" not in b for b in d["output"]["content_blocks"])


# ---------------------------------------------------------------------------
# D-M1 — namespace
# ---------------------------------------------------------------------------

class TestFunctionCallNamespace:

    def _calls(self) -> list[dict[str, Any]]:
        return [
            {"type": "function_call", "call_id": "c1", "name": "search", "namespace": "github", "arguments": "{}"},
            {"type": "function_call", "call_id": "c2", "name": "search", "namespace": "jira", "arguments": "{}"},
        ]

    def test_namespace_is_kept_on_tool_calls(self) -> None:
        d = _normalize(self._calls())
        assert [(tc["name"], tc.get("namespace")) for tc in d["output"]["tool_calls"]] == [
            ("search", "github"), ("search", "jira"),
        ]

    def test_namespace_is_kept_on_tool_call_content_blocks(self) -> None:
        d = _normalize(self._calls())
        blocks = [b for b in d["output"]["content_blocks"] if b["type"] == "tool_call"]
        assert [b.get("namespace") for b in blocks] == ["github", "jira"]

    def test_namespace_is_kept_in_the_tool_call_summary(self) -> None:
        from leer.integrations.normalize import summarize_tool_call

        summary = summarize_tool_call({"id": "c1", "name": "search", "namespace": "github", "arguments": {}})
        assert summary["namespace"] == "github"
        assert "namespace" not in summarize_tool_call({"id": "c1", "name": "search", "arguments": {}})

    def test_no_namespace_means_no_key(self) -> None:
        d = _normalize([{"type": "function_call", "call_id": "c1", "name": "search", "arguments": "{}"}])
        assert "namespace" not in d["output"]["tool_calls"][0]


# ---------------------------------------------------------------------------
# D-H2 — custom tool calls
# ---------------------------------------------------------------------------

class TestCustomToolCall:

    def test_custom_tool_call_is_a_tool_call(self) -> None:
        d = _normalize([{"type": "custom_tool_call", "call_id": "call_sql", "name": "run_sql", "input": "SELECT 1"}])
        assert d["output"]["tool_calls"] == [{"id": "call_sql", "name": "run_sql", "arguments": "SELECT 1"}]
        assert d["output"]["content_blocks"] == [
            {"type": "tool_call", "id": "call_sql", "name": "run_sql", "arguments": "SELECT 1"},
        ]

    def test_custom_tool_call_json_input_is_parsed_like_function_arguments(self) -> None:
        d = _normalize([{"type": "custom_tool_call", "call_id": "c", "name": "t", "input": '{"a": 1}'}])
        assert d["output"]["tool_calls"][0]["arguments"] == {"a": 1}

    def test_custom_tool_call_keeps_namespace(self) -> None:
        d = _normalize([{"type": "custom_tool_call", "call_id": "c", "name": "t", "namespace": "db", "input": "x"}])
        assert d["output"]["tool_calls"][0]["namespace"] == "db"
