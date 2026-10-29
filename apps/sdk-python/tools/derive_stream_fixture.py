"""Derive a streaming drift fixture from a non-streaming one.

    uv run python tools/derive_stream_fixture.py tests/fixtures/provider_payloads/raw/<stem>.json ...

Writes ``tests/fixtures/provider_payloads/stream/<stem>.json``: the SSE event
list a provider would send for the same final response, following each
provider's event protocol (text and JSON arguments split across several
deltas). The drift suite replays it through the real SDK and checks the
streamed record against a golden and against the non-streamed twin.

Derived events stand in until the opt-in recorder captures real streams in
the same format. See ``docs/04-execution/version-drift-step-0-audit.md``.
"""

from __future__ import annotations

import json
import sys
from itertools import count
from pathlib import Path
from typing import Any

STREAM_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "provider_payloads" / "stream"


def _pieces(text: str, n: int = 3) -> list[str]:
    """Split ``text`` into up to ``n`` non-empty chunks."""
    if not text:
        return []
    size = max(1, -(-len(text) // n))
    return [text[i:i + size] for i in range(0, len(text), size)]


# ---------------------------------------------------------------------------
# OpenAI chat completions
# ---------------------------------------------------------------------------

def _chat_events(response: dict[str, Any]) -> list[dict[str, Any]]:
    envelope = {k: response[k] for k in ("id", "created", "model") if k in response}
    envelope["object"] = "chat.completion.chunk"

    def chunk(delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
        return {**envelope, "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason, "logprobs": None}]}

    choice = response["choices"][0]
    message = choice["message"]
    events = [chunk({"role": "assistant", "content": "", "refusal": None})]
    for piece in _pieces(message.get("content") or ""):
        events.append(chunk({"content": piece}))
    for piece in _pieces(message.get("refusal") or ""):
        events.append(chunk({"refusal": piece}))
    for i, tc in enumerate(message.get("tool_calls") or []):
        events.append(chunk({"tool_calls": [{"index": i, "id": tc["id"], "type": tc["type"],
                                             "function": {"name": tc["function"]["name"], "arguments": ""}}]}))
        for piece in _pieces(tc["function"]["arguments"]):
            events.append(chunk({"tool_calls": [{"index": i, "function": {"arguments": piece}}]}))
    events.append(chunk({}, choice["finish_reason"]))
    if response.get("usage"):
        events.append({**envelope, "choices": [], "usage": response["usage"]})
    return events


# ---------------------------------------------------------------------------
# OpenAI responses
# ---------------------------------------------------------------------------

def _responses_events(response: dict[str, Any]) -> list[dict[str, Any]]:
    seq = count()
    events: list[dict[str, Any]] = [{
        "type": "response.created", "sequence_number": next(seq),
        "response": {**response, "status": "in_progress", "output": [], "usage": None},
    }]

    def emit(event_type: str, **fields: Any) -> None:
        events.append({"type": event_type, "sequence_number": next(seq), **fields})

    for i, item in enumerate(response["output"]):
        at = {"output_index": i, "item_id": item["id"]}
        kind = item["type"]
        skeleton = {**item, "status": "in_progress"} if "status" in item else dict(item)
        if kind == "message":
            skeleton["content"] = []
        elif kind == "function_call":
            skeleton["arguments"] = ""
        elif kind == "custom_tool_call":
            skeleton["input"] = ""
        emit("response.output_item.added", output_index=i, item=skeleton)

        if kind == "message":
            for j, part in enumerate(item["content"]):
                field = "text" if part["type"] == "output_text" else "refusal"
                name = "output_text" if field == "text" else "refusal"
                emit("response.content_part.added", **at, content_index=j, part={**part, field: ""})
                for piece in _pieces(part[field]):
                    extra = {"logprobs": []} if field == "text" else {}
                    emit(f"response.{name}.delta", **at, content_index=j, delta=piece, **extra)
                extra = {"logprobs": []} if field == "text" else {}
                emit(f"response.{name}.done", **at, content_index=j, **{field: part[field]}, **extra)
                emit("response.content_part.done", **at, content_index=j, part=part)
        elif kind == "function_call":
            for piece in _pieces(item["arguments"]):
                emit("response.function_call_arguments.delta", **at, delta=piece)
            emit("response.function_call_arguments.done", **at, name=item["name"], arguments=item["arguments"])
        elif kind == "custom_tool_call":
            for piece in _pieces(item["input"]):
                emit("response.custom_tool_call_input.delta", **at, delta=piece)
            emit("response.custom_tool_call_input.done", **at, input=item["input"])

        emit("response.output_item.done", output_index=i, item=item)

    terminal = {"completed": "response.completed", "incomplete": "response.incomplete",
                "failed": "response.failed"}[response["status"]]
    emit(terminal, response=response)
    return events


# ---------------------------------------------------------------------------
# Anthropic messages
# ---------------------------------------------------------------------------

_INPUT_USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _anthropic_events(message: dict[str, Any]) -> list[dict[str, Any]]:
    usage = message.get("usage") or {}
    start_usage = {k: usage[k] for k in _INPUT_USAGE_KEYS if k in usage}
    events: list[dict[str, Any]] = [{"type": "message_start", "message": {
        **message, "content": [], "stop_reason": None, "stop_sequence": None, "stop_details": None,
        "usage": {**start_usage, "output_tokens": 0},
    }}]

    for i, block in enumerate(message["content"]):
        kind = block["type"]
        if kind == "text":
            events.append({"type": "content_block_start", "index": i, "content_block": {**block, "text": ""}})
            for piece in _pieces(block["text"]):
                events.append({"type": "content_block_delta", "index": i,
                               "delta": {"type": "text_delta", "text": piece}})
        elif kind == "thinking":
            events.append({"type": "content_block_start", "index": i,
                           "content_block": {"type": "thinking", "thinking": "", "signature": ""}})
            for piece in _pieces(block["thinking"]):
                events.append({"type": "content_block_delta", "index": i,
                               "delta": {"type": "thinking_delta", "thinking": piece}})
            events.append({"type": "content_block_delta", "index": i,
                           "delta": {"type": "signature_delta", "signature": block.get("signature", "")}})
        elif kind in ("tool_use", "server_tool_use"):
            events.append({"type": "content_block_start", "index": i, "content_block": {**block, "input": {}}})
            for piece in _pieces(json.dumps(block["input"])):
                events.append({"type": "content_block_delta", "index": i,
                               "delta": {"type": "input_json_delta", "partial_json": piece}})
        else:
            events.append({"type": "content_block_start", "index": i, "content_block": block})
        events.append({"type": "content_block_stop", "index": i})

    delta = {"stop_reason": message["stop_reason"], "stop_sequence": message.get("stop_sequence")}
    if message.get("stop_details") is not None:
        delta["stop_details"] = message["stop_details"]
    events.append({"type": "message_delta", "delta": delta, "usage": dict(usage)})
    events.append({"type": "message_stop"})
    return events


_DERIVERS = {
    "openai_chat": _chat_events,
    "openai_responses": _responses_events,
    "anthropic": _anthropic_events,
}


def derive(raw_path: Path) -> dict[str, Any]:
    fixture = json.loads(raw_path.read_text(encoding="utf-8"))
    return {
        "kind": fixture["kind"],
        "provenance": {
            **fixture["provenance"],
            "source": f"derived:raw/{raw_path.name}",
            "notes": "Streamed twin of the raw fixture with the same name (see tools/derive_stream_fixture.py).",
        },
        "events": _DERIVERS[fixture["kind"]](fixture["response"]),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    STREAM_DIR.mkdir(parents=True, exist_ok=True)
    for arg in argv:
        raw_path = Path(arg)
        out = STREAM_DIR / raw_path.name
        out.write_text(json.dumps(derive(raw_path), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
