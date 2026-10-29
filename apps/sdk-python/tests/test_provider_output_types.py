"""New provider output types (drift D-M2, D-M3; ADR-002).

Provider-run tools become one ``provider_tool`` content part per execution and
stay out of ``output.tool_calls``. OpenAI ``reasoning`` joins the thinking
channel, caller-run OpenAI tools become ordinary tool calls, and Anthropic
``stop_details`` fills ``meta.refusal_category``.
"""

from __future__ import annotations

from typing import Any

from leer.integrations.normalize import normalize_anthropic, normalize_openai

REQ_OAI = {"model": "gpt-test", "input": "hi"}
REQ_ANT = {"model": "claude-test", "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]}


def _oai(*items: dict[str, Any]) -> dict[str, Any]:
    out = normalize_openai(REQ_OAI, {"id": "resp_1", "object": "response", "model": "gpt-test",
                                     "status": "completed", "output": list(items)}).to_dict()
    return out


def _ant(*blocks: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return normalize_anthropic(REQ_ANT, {"id": "msg_1", "type": "message", "model": "claude-test",
                                         "content": list(blocks), "stop_reason": "end_turn",
                                         **extra}).to_dict()


def _types(call: dict[str, Any]) -> list[str]:
    return [b["type"] for b in call["output"]["content_blocks"]]


# ---------------------------------------------------------------------------
# OpenAI provider-run tools
# ---------------------------------------------------------------------------

class TestOpenAIProviderTools:
    def test_web_search_call(self) -> None:
        call = _oai({"id": "ws_1", "type": "web_search_call", "status": "completed",
                     "action": {"type": "search", "query": "leer execution record"}})
        (block,) = call["output"]["content_blocks"]
        assert block == {
            "type": "provider_tool",
            "id": "ws_1",
            "name": "web_search",
            "input": {"type": "search", "query": "leer execution record"},
            "status": "completed",
            "provider": "openai",
            "provider_part_type": "web_search_call",
            "preview_text": "web_search: leer execution record",
        }
        assert call["output"]["tool_calls"] == []

    def test_mcp_call_keeps_server_output_and_error(self) -> None:
        call = _oai(
            {"id": "mcp_1", "type": "mcp_call", "name": "read_wiki", "server_label": "deepwiki",
             "arguments": '{"repo": "leer"}', "output": "page text", "status": "completed"},
            {"id": "mcp_2", "type": "mcp_call", "name": "read_wiki", "server_label": "deepwiki",
             "arguments": "{}", "status": "failed",
             "error": {"type": "http_error", "code": 502, "message": "Bad gateway"}},
        )
        ok, failed = call["output"]["content_blocks"]
        assert ok["name"] == "read_wiki"
        assert ok["server"] == "deepwiki"
        assert ok["input"] == {"repo": "leer"}
        assert ok["output"] == "page text"
        assert "error" not in ok
        assert failed["status"] == "failed"
        assert failed["error"] == "Bad gateway"
        assert call["output"]["tool_calls"] == []

    def test_file_search_and_code_interpreter(self) -> None:
        call = _oai(
            {"id": "fs_1", "type": "file_search_call", "status": "completed", "queries": ["refund policy"],
             "results": [{"file_id": "file_1", "text": "30 days"}]},
            {"id": "ci_1", "type": "code_interpreter_call", "status": "completed", "container_id": "cntr_1",
             "code": "print(1+1)", "outputs": [{"type": "logs", "logs": "2"}]},
        )
        fs, ci = call["output"]["content_blocks"]
        assert (fs["name"], fs["input"], fs["output"]) == (
            "file_search", {"queries": ["refund policy"]}, [{"file_id": "file_1", "text": "30 days"}])
        assert (ci["name"], ci["input"], ci["output"]) == (
            "code_interpreter", {"code": "print(1+1)", "container_id": "cntr_1"}, [{"type": "logs", "logs": "2"}])

    def test_order_is_kept_around_text(self) -> None:
        call = _oai(
            {"id": "ws_1", "type": "web_search_call", "status": "completed", "action": {"type": "search", "query": "q"}},
            {"id": "msg_1", "type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "Found it."}]},
        )
        assert _types(call) == ["provider_tool", "text"]
        assert call["output"]["text"] == "Found it."


# ---------------------------------------------------------------------------
# OpenAI reasoning and caller-run tools
# ---------------------------------------------------------------------------

class TestOpenAIReasoning:
    def test_summary_becomes_thinking(self) -> None:
        call = _oai({"id": "rs_1", "type": "reasoning", "summary": [
            {"type": "summary_text", "text": "Check the docs."},
            {"type": "summary_text", "text": "Then answer."},
        ]})
        assert call["output"]["content_blocks"] == [{"type": "thinking", "thinking": "Check the docs.\n\nThen answer."}]
        assert call["output"]["text"] is None

    def test_reasoning_text_used_without_summary(self) -> None:
        call = _oai({"id": "rs_1", "type": "reasoning", "summary": [],
                     "content": [{"type": "reasoning_text", "text": "raw chain"}]})
        assert call["output"]["content_blocks"] == [{"type": "thinking", "thinking": "raw chain"}]

    def test_hidden_reasoning_is_redacted_thinking(self) -> None:
        call = _oai({"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "gAAA…"})
        assert call["output"]["content_blocks"] == [{"type": "redacted_thinking"}]


class TestOpenAICallerRunTools:
    def test_builtin_client_tools_are_tool_calls(self) -> None:
        call = _oai(
            {"id": "cu_1", "type": "computer_call", "call_id": "call_cu", "status": "completed",
             "pending_safety_checks": [], "action": {"type": "click", "x": 1, "y": 2, "button": "left"}},
            {"id": "ls_1", "type": "local_shell_call", "call_id": "call_ls", "status": "completed",
             "action": {"type": "exec", "command": ["ls"], "env": {}}},
            {"id": "sh_1", "type": "shell_call", "call_id": "call_sh", "status": "completed",
             "action": {"commands": ["ls -la"]}},
            {"id": "ap_1", "type": "apply_patch_call", "call_id": "call_ap", "status": "completed",
             "operation": {"type": "update_file", "path": "a.py", "diff": "@@"}},
        )
        assert [(tc["id"], tc["name"]) for tc in call["output"]["tool_calls"]] == [
            ("call_cu", "computer"), ("call_ls", "local_shell"), ("call_sh", "shell"), ("call_ap", "apply_patch"),
        ]
        assert call["output"]["tool_calls"][0]["arguments"] == {"type": "click", "x": 1, "y": 2, "button": "left"}
        assert call["output"]["tool_calls"][3]["arguments"] == {"type": "update_file", "path": "a.py", "diff": "@@"}
        assert _types(call) == ["tool_call"] * 4

    def test_batched_computer_actions(self) -> None:
        call = _oai({"id": "cu_1", "type": "computer_call", "call_id": "call_cu", "status": "completed",
                     "pending_safety_checks": [], "actions": [{"type": "screenshot"}, {"type": "wait"}]})
        assert call["output"]["tool_calls"][0]["arguments"] == [{"type": "screenshot"}, {"type": "wait"}]

    def test_unknown_items_still_fall_back_to_file(self) -> None:
        call = _oai({"id": "x_1", "type": "brand_new_item"})
        (block,) = call["output"]["content_blocks"]
        assert block["type"] == "file"
        assert block["provider_part_type"] == "brand_new_item"


# ---------------------------------------------------------------------------
# Anthropic server tools
# ---------------------------------------------------------------------------

_SEARCH_RESULT = {"type": "web_search_result", "url": "https://leer.dev", "title": "Leer",
                  "encrypted_content": "EqgfCioIARgB…", "page_age": None}


class TestAnthropicServerTools:
    def test_call_and_result_merge_into_one_part(self) -> None:
        call = _ant(
            {"type": "text", "text": "Searching."},
            {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search",
             "input": {"query": "leer execution record"}},
            {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [_SEARCH_RESULT]},
            {"type": "text", "text": "Leer records runs."},
        )
        assert _types(call) == ["text", "provider_tool", "text"]
        block = call["output"]["content_blocks"][1]
        assert block == {
            "type": "provider_tool",
            "id": "srvtoolu_1",
            "name": "web_search",
            "input": {"query": "leer execution record"},
            "output": [{"type": "web_search_result", "url": "https://leer.dev", "title": "Leer", "page_age": None}],
            "provider": "anthropic",
            "provider_part_type": "server_tool_use",
            "preview_text": "web_search: leer execution record",
        }
        assert call["output"]["tool_calls"] == []
        assert call["output"]["text"] == "Searching.\n\nLeer records runs."

    def test_error_result(self) -> None:
        call = _ant(
            {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "q"}},
            {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1",
             "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}},
        )
        (block,) = call["output"]["content_blocks"]
        assert block["error"] == "max_uses_exceeded"

    def test_result_without_call_is_its_own_part(self) -> None:
        call = _ant({"type": "code_execution_tool_result", "tool_use_id": "srvtoolu_9",
                     "content": {"type": "code_execution_result", "stdout": "2", "stderr": "", "return_code": 0,
                                 "content": []}})
        (block,) = call["output"]["content_blocks"]
        assert block["type"] == "provider_tool"
        assert block["id"] == "srvtoolu_9"
        assert block["provider_part_type"] == "code_execution_tool_result"
        assert block["output"]["stdout"] == "2"

    def test_client_tool_use_still_a_tool_call(self) -> None:
        call = _ant({"type": "tool_use", "id": "toolu_1", "name": "lookup", "input": {"a": 1}})
        assert [tc["name"] for tc in call["output"]["tool_calls"]] == ["lookup"]

    def test_container_upload_is_a_provider_file(self) -> None:
        call = _ant({"type": "container_upload", "file_id": "file_abc"})
        (block,) = call["output"]["content_blocks"]
        assert block["type"] == "file"
        assert block["source"] == {"kind": "provider_file", "value": "file_abc", "label": None}


# ---------------------------------------------------------------------------
# Anthropic stop_details (D-M3)
# ---------------------------------------------------------------------------

class TestAnthropicStopDetails:
    def test_refusal_category_and_explanation(self) -> None:
        call = _ant(stop_reason="refusal", stop_details={
            "type": "refusal", "category": "cyber", "explanation": "This looks like malware development."})
        assert call["meta"]["refusal"] == "This looks like malware development."
        assert call["meta"]["refusal_category"] == "cyber"
        assert call["output"]["text"] == "[refusal] This looks like malware development."

    def test_model_text_wins_over_explanation(self) -> None:
        call = _ant({"type": "text", "text": "I can't help with that."}, stop_reason="refusal",
                    stop_details={"type": "refusal", "category": "bio", "explanation": "x"})
        assert call["meta"]["refusal"] == "I can't help with that."
        assert call["meta"]["refusal_category"] == "bio"

    def test_no_refusal_no_category(self) -> None:
        call = _ant({"type": "text", "text": "ok"})
        assert call["meta"]["refusal_category"] is None

    def test_openai_has_no_category(self) -> None:
        call = _oai({"id": "msg_1", "type": "message", "role": "assistant",
                     "content": [{"type": "refusal", "refusal": "No."}]})
        assert call["meta"]["refusal"] == "No."
        assert call["meta"]["refusal_category"] is None
