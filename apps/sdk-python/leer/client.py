from __future__ import annotations

import base64
import sys
from dataclasses import dataclass
from typing import Any

import httpx

from leer.models import TraceArtifact, TraceEvent, TraceRun, TraceStep


@dataclass
class _Config:
    api_base_url: str = ""
    project_slug: str = ""


_config = _Config()


def configure(api_base_url: str, project_slug: str) -> None:
    _config.api_base_url = api_base_url.rstrip("/")
    _config.project_slug = project_slug


def _serialize_dt(dt: Any) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _serialize_step(s: TraceStep) -> dict[str, Any]:
    return {
        "id": s.id,
        "parent_step_id": s.parent_step_id,
        "sequence_index": s.sequence_index,
        "name": s.name,
        "step_type": s.step_type,
        "status": s.status,
        "started_at": _serialize_dt(s.started_at),
        "ended_at": _serialize_dt(s.ended_at),
        "duration_ms": s.duration_ms,
        "input_summary": s.input_summary,
        "output_summary": s.output_summary,
        "error_summary": s.error_summary,
        "metadata": s.metadata,
    }


def _serialize_event(e: TraceEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "step_id": e.step_id,
        "event_type": e.event_type,
        "sequence_index": e.sequence_index,
        "timestamp": _serialize_dt(e.timestamp),
        "payload": e.payload,
    }


def _serialize_artifact(a: TraceArtifact) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": a.id,
        "step_id": a.step_id,
        "artifact_type": a.artifact_type,
        "role": a.role,
        "format": a.format,
        "storage_kind": a.storage_kind,
        "sequence_index": a.sequence_index,
        "mime_type": a.mime_type,
        "filename": a.filename,
        "inline_data": a.inline_data,
        "blob_path": a.blob_path,
        "preview_text": a.preview_text,
        "metadata": a.metadata,
    }
    if a.binary_data is not None:
        d["binary_data_b64"] = base64.b64encode(a.binary_data).decode("ascii")
    return d


def _build_payload(run: TraceRun) -> dict[str, Any]:
    return {
        "project_slug": _config.project_slug,
        "run": {
            "id": run.id,
            "workflow_name": run.workflow_name,
            "status": run.status,
            "trigger_type": run.trigger_type,
            "source": run.source,
            "started_at": _serialize_dt(run.started_at),
            "ended_at": _serialize_dt(run.ended_at),
            "input_summary": run.input_summary,
            "output_summary": run.output_summary,
            "error_summary": run.error_summary,
            "metadata": run.metadata,
        },
        "steps": [_serialize_step(s) for s in run.steps],
        "events": [_serialize_event(e) for e in run.events],
        "artifacts": [_serialize_artifact(a) for a in run.artifacts],
        "replay": None,
    }


def submit(run: TraceRun) -> None:
    if not _config.api_base_url:
        print("[leer] warning: api_base_url not configured, skipping submission", file=sys.stderr)
        return

    url = f"{_config.api_base_url}/v1/ingest/runs"
    payload = _build_payload(run)

    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[leer] submission failed: {exc}", file=sys.stderr)
