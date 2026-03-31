"""First-class tool step helper for Leer SDK.

Usage::

    from leer import tool_step

    with tool_step("get_weather", tool_call_id="call_123") as s:
        s.input = {"city": "Paris"}
        result = get_weather(city="Paris")
        s.output = result

The tool step appears in the run timeline as a real ``tool`` step with
request/response artifacts and readable summaries.
"""

from __future__ import annotations

import json
import traceback as _tb
from contextlib import contextmanager
from typing import Any, Generator

from leer.artifacts import attach_artifact, create_json_artifact
from leer.context import current_step, get_current_run, next_event_index, pop_step, push_step
from leer.models import TraceEvent, TraceStep, _now, make_json_safe


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@contextmanager
def tool_step(
    tool_name: str,
    *,
    tool_call_id: str | None = None,
    source_provider: str | None = None,
    source_model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[TraceStep, None, None]:
    """Trace a tool execution as a first-class step.

    Creates a step with ``step_type="tool"`` and attaches tool-specific
    metadata.  On exit, request/response artifacts and summaries are
    generated from the step's ``.input`` and ``.output`` attributes.

    If the tool raises, the exception propagates unchanged. Leer captures
    error metadata and artifacts on a best-effort basis.
    """
    run = get_current_run()

    tool_meta: dict[str, Any] = {"tool_name": tool_name}
    if tool_call_id is not None:
        tool_meta["tool_call_id"] = tool_call_id
    if source_provider is not None:
        tool_meta["provider"] = source_provider
    if source_model is not None:
        tool_meta["model"] = source_model
    if metadata:
        tool_meta.update(metadata)

    if run is None:
        dummy = TraceStep(name=tool_name, step_type="tool", metadata=tool_meta)
        yield dummy
        return

    parent = current_step()

    s = TraceStep(
        name=tool_name,
        step_type="tool",
        sequence_index=len(run.steps),
        parent_step_id=parent.id if parent else None,
        status="running",
        started_at=_now(),
        metadata=tool_meta,
    )

    run.steps.append(s)
    push_step(s)

    _emit("step.created", s.id, run)
    _emit("step.started", s.id, run)

    try:
        yield s
    except Exception:
        s.status = "failed"
        s.ended_at = _now()
        s.duration_ms = _compute_duration_ms(s)
        s.error_summary = _build_error_summary()
        _safe_attach_input_artifact(s)
        _safe_attach_error_artifact(s)
        _emit("step.failed", s.id, run)
        pop_step()
        raise
    else:
        s.status = "completed"
        s.ended_at = _now()
        s.duration_ms = _compute_duration_ms(s)

        if s.input is not None and s.input_summary is None:
            s.input_summary = make_json_safe(s.input)
        if s.output is not None and s.output_summary is None:
            s.output_summary = make_json_safe(s.output)

        _safe_attach_input_artifact(s)
        _safe_attach_output_artifact(s)

        _emit("step.completed", s.id, run)
        pop_step()


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def _step_has_artifact(s: TraceStep, artifact_type: str) -> bool:
    """Check if the run already has an artifact of this type for this step."""
    run = get_current_run()
    if run is None:
        return False
    return any(
        a.step_id == s.id and a.artifact_type == artifact_type
        for a in run.artifacts
    )


def _safe_attach_input_artifact(s: TraceStep) -> None:
    """Attach a tool_request artifact from the step's input. Never raises.

    Skips if a tool_request artifact already exists for this step (user-attached).
    """
    try:
        if _step_has_artifact(s, "tool_request"):
            return
        data = s.input if s.input is not None else s.input_summary
        if data is None:
            return
        safe = make_json_safe(data)
        attach_artifact(create_json_artifact(
            artifact_type="tool_request",
            role="input",
            data=safe,
            preview_text=_dict_preview(safe),
            step_id=s.id,
        ))
    except Exception:
        pass


def _safe_attach_output_artifact(s: TraceStep) -> None:
    """Attach a tool_response artifact from the step's output. Never raises.

    Skips if a tool_response artifact already exists for this step (user-attached).
    """
    try:
        if _step_has_artifact(s, "tool_response"):
            return
        data = s.output if s.output is not None else s.output_summary
        if data is None:
            return
        safe = make_json_safe(data)
        attach_artifact(create_json_artifact(
            artifact_type="tool_response",
            role="output",
            data=safe,
            preview_text=_dict_preview(safe),
            step_id=s.id,
        ))
    except Exception:
        pass


def _safe_attach_error_artifact(s: TraceStep) -> None:
    """Attach a tool_error artifact from the step's error_summary. Never raises.

    Skips if a tool_error artifact already exists for this step (user-attached).
    """
    try:
        if _step_has_artifact(s, "tool_error"):
            return
        if s.error_summary is None:
            return
        attach_artifact(create_json_artifact(
            artifact_type="tool_error",
            role="error",
            data=s.error_summary,
            preview_text=_error_preview(s.error_summary),
            step_id=s.id,
        ))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _emit(event_type: str, step_id: str, run: Any) -> None:
    run.events.append(
        TraceEvent(
            event_type=event_type,
            sequence_index=next_event_index(),
            step_id=step_id,
        )
    )


def _compute_duration_ms(s: TraceStep) -> int | None:
    if s.started_at is not None and s.ended_at is not None:
        return int((s.ended_at - s.started_at).total_seconds() * 1000)
    return None


def _build_error_summary() -> dict[str, Any]:
    tb = _tb.format_exc()
    parts = tb.strip().rsplit("\n", 1)
    headline = parts[-1] if parts else "Unknown error"
    error_type, _, message = headline.partition(": ")
    return {
        "error_type": error_type,
        "message": message or error_type,
        "traceback": tb,
    }


def _dict_preview(d: dict[str, Any], max_len: int = 200) -> str:
    """Compact JSON preview that handles nested structures cleanly."""
    try:
        return json.dumps(d, default=str)[:max_len]
    except Exception:
        return str(d)[:max_len]


def _error_preview(summary: dict[str, Any]) -> str:
    et = summary.get("error_type", "Error")
    msg = summary.get("message", "")
    return f"{et}: {msg}"[:200] if msg else str(et)[:200]
