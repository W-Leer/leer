"""Provider-agnostic normalized LLM call shape.

Every provider normalizer produces the same ``NormalizedLLMCall`` so the rest
of the system (artifacts, summaries, UI) never needs to know which provider
was used.

The normalizers accept plain dicts — the future wrappers will call
``.model_dump()`` (or equivalent) on SDK response objects before passing
them here.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Normalized shape
# ---------------------------------------------------------------------------

@dataclass
class LLMInput:
    system: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMOutput:
    text: str | None = None
    content_blocks: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # The structured object a model returned, when determinable: an
    # SDK-provided parsed object (``message.parsed`` / ``output_parsed`` from
    # the ``.parse()`` helpers) when present, else the JSON object/array the
    # canonical ``text`` decodes to. ``None`` for plain-text or tool-only
    # outputs. Provider-agnostic and additive — consumers get a uniform
    # structured payload regardless of which provider produced it.
    parsed: Any | None = None


@dataclass
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    # Tokens served from prompt cache (i.e. cache *reads*). Populated when the
    # provider reports it: OpenAI ``usage.prompt_tokens_details.cached_tokens``
    # (chat completions), ``usage.input_tokens_details.cached_tokens``
    # (responses), Anthropic ``usage.cache_read_input_tokens``. ``None`` means
    # the provider did not report cache-read tokens for this call (the default
    # for non-cached requests). ``0`` means the provider reported it explicitly
    # and no cached tokens were used.
    cached_tokens: int | None = None


@dataclass
class LLMMeta:
    latency_ms: int | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    # Surfaced when a provider explicitly signals a refusal (e.g. OpenAI chat
    # completions ``message.refusal`` or Responses-API ``refusal`` content
    # block). ``None`` means no refusal was reported. The refusal text is
    # also inlined as ``[refusal] ...`` in ``output.text`` for back-compat.
    refusal: str | None = None
    # Policy category of a refusal when the provider names one (Anthropic
    # ``stop_details.category``, e.g. ``"cyber"``). ``None`` otherwise.
    refusal_category: str | None = None
    # ``True`` when the canonical text output is itself a JSON object/array
    # (i.e. ``output.parsed`` is populated). Content-derived and independent
    # of whether a schema/``response_format`` was requested — a structured
    # signal consumers can read without re-parsing ``output.text``.
    output_is_json: bool = False


@dataclass
class NormalizedLLMCall:
    provider: str
    model: str | None
    input: LLMInput
    output: LLMOutput
    usage: LLMUsage
    meta: LLMMeta

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Traverse nested dicts safely."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def _extract_params(request: dict[str, Any], known: frozenset[str]) -> dict[str, Any]:
    return {k: v for k, v in request.items() if k in known}


def _detect_structured_output(
    text: str | None,
    sdk_parsed: Any = None,
) -> tuple[Any, bool]:
    """Determine the structured payload for an LLM output.

    Prefers an SDK-provided parsed object (``message.parsed`` /
    ``output_parsed`` from the ``.parse()`` helpers) when it is a dict/list;
    otherwise decodes the canonical ``text`` when it is a whole JSON
    object/array. Returns ``(parsed_object, is_json)``.

    Only object/array JSON counts as "structured" — scalar JSON (e.g. a bare
    ``42`` or ``"hi"``) and refusal-prefixed text are intentionally not
    flagged, so ordinary prose is never mislabeled.
    """
    if isinstance(sdk_parsed, (dict, list)):
        return sdk_parsed, True
    if isinstance(text, str):
        stripped = text.strip()
        if stripped[:1] in ("{", "["):
            try:
                obj = json.loads(stripped)
            except (ValueError, TypeError):
                return None, False
            if isinstance(obj, (dict, list)):
                return obj, True
    return None, False


def _parse_arguments(raw: Any) -> Any:
    """Parse JSON-string arguments into structured data when possible."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


def _resolve_model(response: dict[str, Any], request: dict[str, Any]) -> str | None:
    return response.get("model") or request.get("model") or None


def _arguments_hash(args: Any) -> str | None:
    """Deterministic short hash of tool-call arguments for compact comparison."""
    if args is None:
        return None
    try:
        canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        canonical = str(args)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def summarize_tool_call(tc: dict[str, Any]) -> dict[str, Any]:
    """Build a compact summary dict for one normalized tool call.

    Shape: ``{name, namespace?, id?, arguments_hash?}``
    Always includes ``name``; the others are present only when the source
    tool call provides them.
    """
    summary: dict[str, Any] = {"name": tc.get("name", "?")}
    if tc.get("namespace"):
        summary["namespace"] = tc["namespace"]
    call_id = tc.get("id")
    if call_id is not None:
        summary["id"] = call_id
    args = tc.get("arguments")
    h = _arguments_hash(args)
    if h is not None:
        summary["arguments_hash"] = h
    return summary


def create_tool_call_artifacts(
    normalized: "NormalizedLLMCall",
    *,
    step_id: str | None = None,
) -> list[Any]:
    """Create one ``tool_call`` artifact per emitted tool call.

    Each artifact is a lightweight JSON record attached to the LLM step,
    giving every tool-call intent its own addressable, inspectable record.

    Returns a list of ``TraceArtifact`` ready to be attached.
    """
    from leer.artifacts import create_json_artifact

    artifacts: list[Any] = []
    for i, tc in enumerate(normalized.output.tool_calls):
        call_id = tc.get("id")
        name = tc.get("name", "?")
        args = tc.get("arguments")
        args_hash = _arguments_hash(args)

        data: dict[str, Any] = {
            "tool_name": name,
            "arguments": args,
        }
        if call_id is not None:
            data["tool_call_id"] = call_id
        if args_hash is not None:
            data["arguments_hash"] = args_hash
        data["call_index"] = i

        meta: dict[str, Any] = {"tool_name": name, "call_index": i}
        if call_id is not None:
            meta["tool_call_id"] = call_id
        if normalized.provider:
            meta["provider"] = normalized.provider
        if normalized.model:
            meta["model"] = normalized.model

        preview = f"{name}({call_id or ''})" if call_id else name
        art = create_json_artifact(
            artifact_type="tool_call",
            role="output",
            data=data,
            preview_text=preview[:200],
            metadata=meta,
            step_id=step_id,
        )
        artifacts.append(art)

    return artifacts


# ---------------------------------------------------------------------------
# Canonical content-part helpers
# ---------------------------------------------------------------------------

_IMAGE_MIMES = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
})

_DOC_MIMES = frozenset({
    "application/pdf",
})


def _canonical_type_from_mime(mime: str | None) -> str:
    """Map MIME to a canonical part type.

    Step 2 scope: only ``image``, ``document``, and ``file``.
    Audio/video may get dedicated types in a future step; for now they
    fall through to generic ``file``.
    """
    if not mime:
        return "file"
    if mime in _IMAGE_MIMES or mime.startswith("image/"):
        return "image"
    if mime in _DOC_MIMES:
        return "document"
    return "file"


def _make_source(kind: str, value: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "value": value, "label": None}


def _media_part(
    part_type: str,
    *,
    mime_type: str | None = None,
    source: dict[str, Any] | None = None,
    provider: str | None = None,
    provider_part_type: str | None = None,
    filename: str | None = None,
    preview_text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical media content part.  Omits None-valued optional fields."""
    d: dict[str, Any] = {"type": part_type}
    if mime_type is not None:
        d["mime_type"] = mime_type
    if source is not None:
        d["source"] = source
    if provider is not None:
        d["provider"] = provider
    if provider_part_type is not None:
        d["provider_part_type"] = provider_part_type
    if filename is not None:
        d["filename"] = filename
    if preview_text is not None:
        d["preview_text"] = preview_text
    if metadata:
        d["metadata"] = metadata
    return d


# ---------------------------------------------------------------------------
# Provider-run tools (ADR-002)
# ---------------------------------------------------------------------------

# Opaque provider blobs (e.g. encrypted search-page content). They carry no
# meaning outside the provider and stay in the raw response artifact.
_OPAQUE_KEYS = frozenset({"encrypted_content", "encrypted_index"})


def _strip_opaque(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_opaque(v) for k, v in value.items() if k not in _OPAQUE_KEYS}
    if isinstance(value, list):
        return [_strip_opaque(v) for v in value]
    return value


def _provider_tool_preview(name: str | None, tool_input: Any) -> str:
    label = name or "provider tool"
    detail: str | None = None
    if isinstance(tool_input, dict):
        query = tool_input.get("query")
        queries = tool_input.get("queries")
        if isinstance(query, str) and query:
            detail = query
        elif isinstance(queries, list) and queries:
            detail = "; ".join(str(q) for q in queries)
    if detail is None and tool_input:
        detail = json.dumps(tool_input, default=str, ensure_ascii=False)
    return f"{label}: {detail}"[:200] if detail else label


def _provider_tool_part(
    *,
    provider: str,
    provider_part_type: str,
    call_id: str | None,
    name: str | None,
    tool_input: Any,
    status: str | None = None,
    output: Any = None,
    error: str | None = None,
    server: str | None = None,
) -> dict[str, Any]:
    """One tool execution the provider ran itself. Never a ``tool_calls`` entry:
    no local tool step will ever link to it."""
    part: dict[str, Any] = {"type": "provider_tool", "id": call_id, "name": name, "input": tool_input}
    if status is not None:
        part["status"] = status
    if output is not None:
        part["output"] = _strip_opaque(output)
    if error is not None:
        part["error"] = error
    if server is not None:
        part["server"] = server
    part["provider"] = provider
    part["provider_part_type"] = provider_part_type
    part["preview_text"] = _provider_tool_preview(name, tool_input)
    return part


def _error_text(error: Any) -> str | None:
    if isinstance(error, str):
        return error or None
    if isinstance(error, dict):
        return error.get("message") or error.get("error_code") or error.get("type")
    return None


def _summarize_content_for_user(content: Any) -> str:
    """Summarize a user message content array into a readable string with media markers."""
    if isinstance(content, str):
        return content[:200]
    if not isinstance(content, list):
        return str(content)[:200]

    parts: list[str] = []
    for p in content:
        if not isinstance(p, dict):
            continue
        pt = p.get("type", "")
        if pt in ("text", "input_text"):
            t = p.get("text", "")
            if t:
                parts.append(t[:120])
        elif pt == "image_url" or pt == "image":
            parts.append("[image]")
        elif pt == "input_image":
            parts.append("[image]")
        elif pt == "document":
            fname = p.get("filename") or p.get("name") or ""
            label = f"[document: {fname}]" if fname else "[document]"
            parts.append(label)
        elif pt == "file":
            fname = p.get("filename") or p.get("name") or ""
            label = f"[file: {fname}]" if fname else "[file]"
            parts.append(label)
        elif pt == "input_file":
            fname = p.get("filename") or ""
            label = f"[file: {fname}]" if fname else "[file]"
            parts.append(label)
        elif pt == "input_pdf":
            parts.append("[document: PDF]")
        else:
            parts.append(f"[{pt}]")
    return " ".join(parts)[:200] if parts else ""


# ---------------------------------------------------------------------------
# Cache-read token extraction (additive metadata for prompt caching)
# ---------------------------------------------------------------------------


def _extract_cached_tokens_openai(usage_raw: dict[str, Any]) -> int | None:
    """Return cache-read tokens from an OpenAI ``usage`` dict, if reported.

    Chat completions exposes them at ``prompt_tokens_details.cached_tokens``;
    the Responses API exposes them at ``input_tokens_details.cached_tokens``.
    Both shapes are tolerated (and tolerated when the nested object is itself
    malformed, e.g. a list).
    """
    for key in ("prompt_tokens_details", "input_tokens_details"):
        details = usage_raw.get(key)
        if isinstance(details, dict):
            value = details.get("cached_tokens")
            if isinstance(value, int):
                return value
    return None


def _extract_cached_tokens_anthropic(usage_raw: dict[str, Any]) -> int | None:
    """Return cache-read tokens from an Anthropic ``usage`` dict, if reported.

    Anthropic surfaces this as ``cache_read_input_tokens`` (not to be confused
    with ``cache_creation_input_tokens``, which is the cache-*write* cost and
    is intentionally not part of the canonical ``cached_tokens`` field).
    """
    value = usage_raw.get("cache_read_input_tokens")
    if isinstance(value, int):
        return value
    return None


# ---------------------------------------------------------------------------
# OpenAI — parameter sets
# ---------------------------------------------------------------------------

_OPENAI_CHAT_PARAMS = frozenset({
    "temperature", "max_tokens", "max_completion_tokens", "top_p",
    "frequency_penalty", "presence_penalty", "stop", "seed",
    "response_format", "logprobs", "top_logprobs",
})

_OPENAI_RESPONSES_PARAMS = frozenset({
    "temperature", "max_output_tokens", "top_p",
    "truncation", "text", "store", "reasoning",
})


# ---------------------------------------------------------------------------
# OpenAI — public entry point
# ---------------------------------------------------------------------------

def normalize_openai(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize an OpenAI request + response.

    Auto-detects the API shape (chat completions vs. responses) and
    dispatches to the appropriate helper.
    """
    if "output" in response and "choices" not in response:
        return _normalize_openai_responses(request, response, latency_ms=latency_ms)
    return _normalize_openai_chat(request, response, latency_ms=latency_ms)


# ---------------------------------------------------------------------------
# OpenAI — chat completions shape
# ---------------------------------------------------------------------------

def _normalize_openai_chat(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize ``client.chat.completions.create()``."""
    messages = list(request.get("messages", []))

    system: str | None = None
    non_system: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") in ("system", "developer"):
            system = msg.get("content") or system
        else:
            non_system.append(msg)

    params = _extract_params(request, _OPENAI_CHAT_PARAMS)

    choices = response.get("choices") or []
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message", {}) if isinstance(first, dict) else {}

    raw_text = message.get("content") if isinstance(message, dict) else None
    refusal_text = message.get("refusal") if isinstance(message, dict) else None

    # Refusal handling: chat-completions surfaces refusals via a dedicated
    # `message.refusal` field rather than a content block. To match the
    # Responses-API behavior (which inlines `[refusal] <text>`), we surface
    # the refusal in canonical text/content_blocks and tag the meta dict so
    # compare and run-detail can detect it without parsing the prefix.
    has_refusal = isinstance(refusal_text, str) and bool(refusal_text)
    if has_refusal and not raw_text:
        text = f"[refusal] {refusal_text}"
    else:
        text = raw_text

    raw_tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
    tool_calls: list[dict[str, Any]] = []
    for tc in (raw_tool_calls or []):
        if not isinstance(tc, dict):
            continue
        tc_type = tc.get("type", "function")
        if tc_type == "function":
            tool_calls.append({
                "id": tc.get("id"),
                "name": _safe_get(tc, "function", "name"),
                "arguments": _parse_arguments(_safe_get(tc, "function", "arguments")),
            })
        elif tc_type == "custom":
            tool_calls.append({
                "id": tc.get("id"),
                "name": _safe_get(tc, "custom", "name"),
                "arguments": _parse_arguments(_safe_get(tc, "custom", "input")),
            })

    content_blocks: list[dict[str, Any]] = []
    if text:
        content_blocks.append({"type": "text", "text": text})
    for tc in tool_calls:
        content_blocks.append({"type": "tool_call", **tc})

    usage_raw = response.get("usage")
    if not isinstance(usage_raw, dict):
        usage_raw = {}

    finish_reason = first.get("finish_reason") if isinstance(first, dict) else None

    sdk_parsed = message.get("parsed") if isinstance(message, dict) else None
    parsed, output_is_json = _detect_structured_output(text, sdk_parsed)

    return NormalizedLLMCall(
        provider="openai",
        model=_resolve_model(response, request),
        input=LLMInput(
            system=system,
            messages=non_system,
            tools=request.get("tools", []),
            params=params,
        ),
        output=LLMOutput(
            text=text,
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            parsed=parsed,
        ),
        usage=LLMUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
            cached_tokens=_extract_cached_tokens_openai(usage_raw),
        ),
        meta=LLMMeta(
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            request_id=response.get("id"),
            refusal=refusal_text if has_refusal else None,
            output_is_json=output_is_json,
        ),
    )


# ---------------------------------------------------------------------------
# OpenAI — responses shape
# ---------------------------------------------------------------------------

_OPENAI_PROVIDER_TOOL_ITEMS = frozenset({
    "web_search_call", "file_search_call", "code_interpreter_call", "mcp_call",
})

# Built-in tools the caller executes and answers with a ``*_call_output`` item,
# so they link to local tool steps like function calls do.
_OPENAI_CALLER_TOOL_ITEMS = {
    "computer_call": "computer",
    "local_shell_call": "local_shell",
    "shell_call": "shell",
    "apply_patch_call": "apply_patch",
}


def _openai_provider_tool(item: dict[str, Any]) -> dict[str, Any]:
    item_type = item["type"]
    output: Any = None
    error: str | None = None
    server: str | None = None
    if item_type == "web_search_call":
        name, tool_input = "web_search", item.get("action") or {}
    elif item_type == "file_search_call":
        name, tool_input, output = "file_search", {"queries": item.get("queries")}, item.get("results")
    elif item_type == "code_interpreter_call":
        name, output = "code_interpreter", item.get("outputs")
        tool_input = {"code": item.get("code"), "container_id": item.get("container_id")}
    else:
        name, tool_input = item.get("name"), _parse_arguments(item.get("arguments"))
        output, error, server = item.get("output"), _error_text(item.get("error")), item.get("server_label")
    return _provider_tool_part(
        provider="openai",
        provider_part_type=item_type,
        call_id=item.get("id"),
        name=name,
        tool_input=tool_input,
        status=item.get("status"),
        output=output,
        error=error,
        server=server,
    )


def _openai_reasoning_part(item: dict[str, Any]) -> dict[str, Any]:
    """``reasoning`` joins the thinking channel. Summaries are what OpenAI
    shows; ``reasoning_text`` only comes from open-weight models."""
    texts = [s["text"] for s in (item.get("summary") or []) if isinstance(s, dict) and s.get("text")]
    if not texts:
        texts = [c["text"] for c in (item.get("content") or []) if isinstance(c, dict) and c.get("text")]
    if not texts:
        return {"type": "redacted_thinking"}
    return {"type": "thinking", "thinking": "\n\n".join(texts)}


def _normalize_openai_responses(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize ``client.responses.create()``."""
    system = request.get("instructions")

    raw_input = request.get("input", [])
    if isinstance(raw_input, str):
        messages: list[dict[str, Any]] = [{"role": "user", "content": raw_input}]
    elif isinstance(raw_input, list):
        non_system: list[dict[str, Any]] = []
        for m in raw_input:
            if not isinstance(m, dict):
                continue
            if m.get("role") == "system":
                system = m.get("content") or system
            else:
                non_system.append(m)
        messages = non_system
    else:
        messages = []

    params = _extract_params(request, _OPENAI_RESPONSES_PARAMS)

    tools_raw = request.get("tools", [])
    tools: list[dict[str, Any]] = []
    for t in (tools_raw or []):
        if not isinstance(t, dict):
            continue
        if t.get("type") == "function":
            tools.append(t.get("function", t))
        else:
            tools.append(t)

    output_items = response.get("output", [])

    text_parts: list[str] = []
    # Text from ``phase == "commentary"`` messages: the preamble newer models
    # send before acting. Kept out of ``output.text`` (which is the answer)
    # unless the response has nothing else.
    commentary_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    content_blocks: list[dict[str, Any]] = []
    refusal_text: str | None = None

    for item in (output_items if isinstance(output_items, list) else []):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")

        if item_type == "message":
            phase = item.get("phase")
            for block in (item.get("content") or []):
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "output_text":
                    t = block.get("text") or ""
                    (commentary_parts if phase == "commentary" else text_parts).append(t)
                    text_block: dict[str, Any] = {"type": "text", "text": t}
                    if isinstance(phase, str):
                        text_block["phase"] = phase
                    content_blocks.append(text_block)
                elif block_type == "output_image":
                    content_blocks.append(_media_part(
                        "image",
                        mime_type=block.get("mime_type"),
                        source=_make_source("provider_file", block.get("file_id")),
                        provider="openai",
                        provider_part_type="output_image",
                        preview_text="image output",
                        metadata={k: v for k, v in {
                            "file_id": block.get("file_id"),
                            "image_url": block.get("image_url"),
                        }.items() if v is not None},
                    ))
                elif block_type == "refusal":
                    raw_refusal = block.get("refusal", "") or ""
                    if isinstance(raw_refusal, str) and raw_refusal:
                        refusal_text = raw_refusal
                    refusal_inline = f"[refusal] {raw_refusal}"
                    # Surface in output.text alongside content_blocks so
                    # run-detail/compare summaries see the refusal even when
                    # no other text was returned. Matches the chat-completions
                    # `message.refusal` path.
                    text_parts.append(refusal_inline)
                    content_blocks.append({"type": "text", "text": refusal_inline})
                elif block_type is not None:
                    content_blocks.append(_media_part(
                        "file",
                        provider="openai",
                        provider_part_type=block_type,
                        preview_text=f"unknown output block: {block_type}",
                        metadata={"raw_type": block_type},
                    ))

        elif item_type in ("function_call", "custom_tool_call"):
            # Custom tools take free-form ``input`` instead of JSON ``arguments``;
            # both are client-executed calls, as on the chat-completions path.
            raw_args = item.get("arguments") if item_type == "function_call" else item.get("input")
            tc = {
                "id": item.get("call_id") or item.get("id"),
                "name": item.get("name"),
                "arguments": _parse_arguments(raw_args),
            }
            # Same-named tools from different namespaces are otherwise
            # indistinguishable.
            if item.get("namespace"):
                tc["namespace"] = item["namespace"]
            tool_calls.append(tc)
            content_blocks.append({"type": "tool_call", **tc})

        elif item_type in _OPENAI_CALLER_TOOL_ITEMS:
            # ``computer_call`` sends one ``action`` or, batched, ``actions``.
            args = item.get("operation") if item_type == "apply_patch_call" else item.get("action")
            if args is None:
                args = item.get("actions")
            tc = {
                "id": item.get("call_id") or item.get("id"),
                "name": _OPENAI_CALLER_TOOL_ITEMS[item_type],
                "arguments": args if args is not None else {},
            }
            tool_calls.append(tc)
            content_blocks.append({"type": "tool_call", **tc})

        elif item_type in _OPENAI_PROVIDER_TOOL_ITEMS:
            content_blocks.append(_openai_provider_tool(item))

        elif item_type == "reasoning":
            content_blocks.append(_openai_reasoning_part(item))

        elif item_type == "image_generation_call":
            content_blocks.append(_media_part(
                "image",
                provider="openai",
                provider_part_type="image_generation_call",
                preview_text="image generation",
                metadata={k: v for k, v in {
                    "result": item.get("result"),
                }.items() if v is not None},
            ))

        elif item_type is not None:
            content_blocks.append(_media_part(
                "file",
                provider="openai",
                provider_part_type=item_type,
                preview_text=f"unknown output item: {item_type}",
                metadata={"raw_type": item_type},
            ))

    if not text_parts:
        text_parts = commentary_parts
    text = "\n\n".join(text_parts) if text_parts else None

    usage_raw = response.get("usage")
    if not isinstance(usage_raw, dict):
        usage_raw = {}

    parsed, output_is_json = _detect_structured_output(text, response.get("output_parsed"))

    return NormalizedLLMCall(
        provider="openai",
        model=_resolve_model(response, request),
        input=LLMInput(
            system=system,
            messages=messages,
            tools=tools,
            params=params,
        ),
        output=LLMOutput(
            text=text,
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            parsed=parsed,
        ),
        usage=LLMUsage(
            prompt_tokens=usage_raw.get("input_tokens"),
            completion_tokens=usage_raw.get("output_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
            cached_tokens=_extract_cached_tokens_openai(usage_raw),
        ),
        meta=LLMMeta(
            latency_ms=latency_ms,
            finish_reason=response.get("status"),
            request_id=response.get("id"),
            refusal=refusal_text,
            output_is_json=output_is_json,
        ),
    )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

_ANTHROPIC_PARAMS = frozenset({
    "temperature", "max_tokens", "top_p", "top_k", "stop_sequences",
    "thinking", "output_format", "output_config",
})


def _is_anthropic_tool_result(block_type: Any) -> bool:
    """Result blocks of provider-run tools (``web_search_tool_result``, …).
    Plain ``tool_result`` is the caller's answer and never appears in output."""
    return isinstance(block_type, str) and block_type.endswith("_tool_result")


def _attach_anthropic_tool_result(
    block: dict[str, Any],
    provider_tools: dict[str, dict[str, Any]],
    content_blocks: list[dict[str, Any]],
) -> None:
    """Merge a result block into its ``provider_tool`` part, so Anthropic has
    the same one-part-per-execution shape as OpenAI."""
    tool_use_id = block.get("tool_use_id")
    content = block.get("content")
    error: str | None = None
    if isinstance(content, dict) and str(content.get("type", "")).endswith("_error"):
        error, content = _error_text(content), None
    elif block.get("is_error"):
        error = "tool returned an error"

    part = provider_tools.get(tool_use_id) if isinstance(tool_use_id, str) else None
    if part is None:
        part = _provider_tool_part(
            provider="anthropic",
            provider_part_type=block.get("type"),
            call_id=tool_use_id,
            name=None,
            tool_input={},
        )
        content_blocks.append(part)
    if content is not None:
        part["output"] = _strip_opaque(content)
    if error is not None:
        part["error"] = error


def normalize_anthropic(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize an Anthropic messages API request + response."""
    system = request.get("system")
    if isinstance(system, list):
        system = " ".join(
            block.get("text", "") for block in system
            if isinstance(block, dict) and block.get("type") == "text"
        ) or None

    messages = list(request.get("messages", []))
    params = _extract_params(request, _ANTHROPIC_PARAMS)

    tools_raw = request.get("tools", [])
    tools = [
        {"name": t.get("name"), "description": t.get("description"), "input_schema": t.get("input_schema")}
        for t in (tools_raw or [])
        if isinstance(t, dict)
    ]

    raw_blocks = response.get("content", [])

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    content_blocks: list[dict[str, Any]] = []
    sdk_parsed: Any = None
    provider_tools: dict[str, dict[str, Any]] = {}

    for block in (raw_blocks if isinstance(raw_blocks, list) else []):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")

        if block_type == "text":
            t = block.get("text", "")
            text_parts.append(t)
            content_blocks.append({"type": "text", "text": t})
            # ``messages.parse()`` attaches the decoded object to the text block.
            if sdk_parsed is None and block.get("parsed_output") is not None:
                sdk_parsed = block["parsed_output"]
        elif block_type == "tool_use":
            tc = {
                "id": block.get("id"),
                "name": block.get("name"),
                "arguments": block.get("input", {}),
            }
            tool_calls.append(tc)
            content_blocks.append({"type": "tool_call", **tc})
        elif block_type in ("server_tool_use", "mcp_tool_use"):
            part = _provider_tool_part(
                provider="anthropic",
                provider_part_type=block_type,
                call_id=block.get("id"),
                name=block.get("name"),
                tool_input=block.get("input") or {},
                server=block.get("server_name"),
            )
            content_blocks.append(part)
            if isinstance(part["id"], str):
                provider_tools[part["id"]] = part
        elif _is_anthropic_tool_result(block_type):
            _attach_anthropic_tool_result(block, provider_tools, content_blocks)
        elif block_type == "container_upload":
            content_blocks.append(_media_part(
                "file",
                source=_make_source("provider_file", block.get("file_id")),
                provider="anthropic",
                provider_part_type="container_upload",
                preview_text="file uploaded to code-execution container",
            ))
        elif block_type == "thinking":
            content_blocks.append({
                "type": "thinking",
                "thinking": block.get("thinking", ""),
            })
        elif block_type == "redacted_thinking":
            content_blocks.append({"type": "redacted_thinking"})
        elif block_type == "image":
            raw_source = block.get("source")
            source_block = raw_source if isinstance(raw_source, dict) else {}
            mime = source_block.get("media_type")
            src_type = source_block.get("type", "")
            if src_type == "url":
                src = _make_source("url", source_block.get("url"))
            elif src_type == "base64":
                src = _make_source("inline")
            else:
                src = _make_source("inline")
            content_blocks.append(_media_part(
                "image",
                mime_type=mime,
                source=src,
                provider="anthropic",
                provider_part_type="image",
                preview_text="image output",
            ))
        elif block_type == "document":
            raw_source = block.get("source")
            source_block = raw_source if isinstance(raw_source, dict) else {}
            mime = source_block.get("media_type") or "application/pdf"
            src_type = source_block.get("type", "")
            if src_type == "url":
                src = _make_source("url", source_block.get("url"))
            else:
                src = _make_source("inline")
            content_blocks.append(_media_part(
                "document",
                mime_type=mime,
                source=src,
                provider="anthropic",
                provider_part_type="document",
                filename=block.get("title") or block.get("name"),
                preview_text="document output",
            ))
        elif block_type is not None:
            content_blocks.append(_media_part(
                _canonical_type_from_mime(block.get("media_type")),
                mime_type=block.get("media_type"),
                provider="anthropic",
                provider_part_type=block_type,
                preview_text=f"unknown block: {block_type}",
                metadata={"raw_type": block_type},
            ))

    text = "\n\n".join(text_parts) if text_parts else None

    # Refusal handling: unlike OpenAI (dedicated `message.refusal` field or
    # `refusal` content block), Anthropic signals a refusal via
    # `stop_reason == "refusal"`. To keep the refusal channel symmetric across
    # providers — so `meta.refusal` detection, the run-detail/compare refusal
    # badge, and the refusal compare-insight fire for Anthropic too — surface
    # it in `meta.refusal`. Mirrors the Step 1 dual-representation rule: the
    # refusal text is the model's explanation (when present), and a
    # `[refusal] ` marker is inlined into `output.text` only when no other
    # content was returned. This keys on `stop_reason`, so the streaming path
    # inherits it via the round-tripped response dict.
    stop_reason = response.get("stop_reason")
    refusal_text: str | None = None
    refusal_category: str | None = None
    if stop_reason == "refusal":
        stop_details = response.get("stop_details")
        if not isinstance(stop_details, dict):
            stop_details = {}
        explanation = stop_details.get("explanation")
        category = stop_details.get("category")
        refusal_category = category if isinstance(category, str) else None
        refusal_text = (
            text
            or (explanation if isinstance(explanation, str) and explanation else None)
            or "Model declined to respond."
        )
        if not text:
            text = f"[refusal] {refusal_text}"
            content_blocks.append({"type": "text", "text": text})

    usage_raw = response.get("usage")
    if not isinstance(usage_raw, dict):
        usage_raw = {}
    prompt_tokens = usage_raw.get("input_tokens")
    completion_tokens = usage_raw.get("output_tokens")
    # Anthropic does not return a precomputed total. Sum what we have, but
    # treat ``0`` as a real value (an empty completion is meaningfully
    # different from a missing one).
    if prompt_tokens is None and completion_tokens is None:
        total: int | None = None
    else:
        total = (prompt_tokens or 0) + (completion_tokens or 0)

    # Structured output arrives either via ``messages.parse()`` (decoded object
    # on the text block) or as JSON text. Structured-via-forced-tool keeps its
    # object in ``tool_calls[].arguments`` and is deliberately not flagged.
    parsed, output_is_json = _detect_structured_output(text, sdk_parsed)

    return NormalizedLLMCall(
        provider="anthropic",
        model=_resolve_model(response, request),
        input=LLMInput(
            system=system,
            messages=messages,
            tools=tools,
            params=params,
        ),
        output=LLMOutput(
            text=text,
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            parsed=parsed,
        ),
        usage=LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cached_tokens=_extract_cached_tokens_anthropic(usage_raw),
        ),
        meta=LLMMeta(
            latency_ms=latency_ms,
            finish_reason=stop_reason,
            request_id=response.get("id"),
            refusal=refusal_text,
            refusal_category=refusal_category,
            output_is_json=output_is_json,
        ),
    )


# ---------------------------------------------------------------------------
# Media artifact materialization
# ---------------------------------------------------------------------------

_ARTIFACT_TYPE_MAP = {
    "image": "output_image",
    "document": "output_document",
}


def _extract_base64_from_response(
    block: dict[str, Any],
    response: dict[str, Any],
    provider: str,
) -> tuple[bytes, str] | None:
    """Try to extract raw bytes + mime from a provider response block.

    Returns ``(raw_bytes, mime_type)`` or ``None`` if bytes are not available.
    """
    if provider == "anthropic":
        raw_source = block.get("source")
        source = raw_source if isinstance(raw_source, dict) else {}
        if source.get("type") == "base64" and source.get("data"):
            mime = source.get("media_type") or "application/octet-stream"
            try:
                raw = base64.b64decode(source["data"])
                return raw, mime
            except Exception:
                return None
    elif provider == "openai":
        if block.get("type") == "output_image":
            b64 = block.get("image_url") or block.get("data")
            if isinstance(b64, str) and len(b64) > 20:
                mime = block.get("mime_type") or "image/png"
                try:
                    raw = base64.b64decode(b64)
                    return raw, mime
                except Exception:
                    return None
        if block.get("type") == "image_generation_call":
            result = block.get("result")
            if isinstance(result, str) and len(result) > 20:
                try:
                    raw = base64.b64decode(result)
                    return raw, "image/png"
                except Exception:
                    return None
    return None


def _find_response_block(
    content_part: dict[str, Any],
    response: dict[str, Any],
    provider: str,
) -> dict[str, Any] | None:
    """Find the original provider response block matching a canonical part."""
    ppt = content_part.get("provider_part_type")
    if not ppt:
        return None

    if provider == "anthropic":
        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == ppt:
                return block
    elif provider == "openai":
        for item in response.get("output", []):
            if not isinstance(item, dict):
                continue
            if item.get("type") == ppt:
                return item
            if item.get("type") == "message":
                for blk in item.get("content", []):
                    if isinstance(blk, dict) and blk.get("type") == ppt:
                        return blk
    return None


def materialize_media_artifacts(
    normalized: NormalizedLLMCall,
    response: dict[str, Any],
    *,
    step_id: str | None = None,
) -> list[Any]:
    """Create binary artifacts for inline/base64 media in content_blocks.

    Mutates ``normalized.output.content_blocks`` in-place to add ``artifact_id``,
    and updates the ``source`` to ``artifact`` kind.

    Returns a list of ``TraceArtifact`` objects ready to be attached.
    """
    from leer.artifacts import create_binary_artifact

    artifacts: list[Any] = []
    provider = normalized.provider

    for part in normalized.output.content_blocks:
        part_type = part.get("type")
        if part_type not in ("image", "document"):
            continue
        if part.get("artifact_id"):
            continue

        resp_block = _find_response_block(part, response, provider)
        if resp_block is None:
            continue

        extracted = _extract_base64_from_response(resp_block, response, provider)
        if extracted is None:
            continue

        raw_bytes, mime = extracted
        artifact_type = _ARTIFACT_TYPE_MAP.get(part_type, f"output_{part_type}")

        art = create_binary_artifact(
            artifact_type=artifact_type,
            data=raw_bytes,
            mime_type=mime,
            role="output",
            filename=part.get("filename"),
            preview_text=part.get("preview_text") or f"{part_type} output",
            step_id=step_id,
        )

        part["artifact_id"] = art.id
        part["source"] = _make_source("artifact", art.id)
        part["size_bytes"] = len(raw_bytes)
        part["mime_type"] = mime

        artifacts.append(art)

    return artifacts
