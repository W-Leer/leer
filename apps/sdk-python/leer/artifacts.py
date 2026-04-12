"""Artifact creation helpers for Leer SDK.

Usage inside a traced step:

    with step("llm_call", step_type="llm") as s:
        ...
        attach_artifact(create_json_artifact(
            artifact_type="llm_request",
            role="input",
            data={"messages": messages, "model": "gpt-4.1"},
            preview_text="system: You are a helpful assistant.",
        ))
"""

from __future__ import annotations

from typing import Any

from leer.context import current_step, get_current_run
from leer.models import TraceArtifact


def create_json_artifact(
    artifact_type: str,
    *,
    role: str | None = None,
    data: dict[str, Any] | list[Any],
    preview_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    step_id: str | None = None,
) -> TraceArtifact:
    """Create an inline JSON artifact.

    ``data`` is required — the DB enforces that inline artifacts have non-null
    ``inline_data``.  Pass a dict for structured payloads or a list for
    sequence data (lists are wrapped as ``{"data": [...]}``) to keep the
    JSONB column consistently object-typed.
    """
    inline = data if isinstance(data, dict) else {"data": data}
    return TraceArtifact(
        artifact_type=artifact_type,
        storage_kind="inline",
        role=role,
        format="json",
        mime_type="application/json",
        inline_data=inline,
        preview_text=preview_text,
        metadata=metadata or {},
        step_id=step_id,
    )


def create_text_artifact(
    artifact_type: str,
    *,
    role: str | None = None,
    text: str,
    preview_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    step_id: str | None = None,
) -> TraceArtifact:
    """Create an inline text artifact stored as JSON with a 'text' key."""
    return TraceArtifact(
        artifact_type=artifact_type,
        storage_kind="inline",
        role=role,
        format="text",
        mime_type="text/plain",
        inline_data={"text": text},
        preview_text=preview_text or text[:200],
        metadata=metadata or {},
        step_id=step_id,
    )


def create_binary_artifact(
    artifact_type: str,
    *,
    data: bytes,
    mime_type: str,
    role: str | None = None,
    filename: str | None = None,
    preview_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    step_id: str | None = None,
) -> TraceArtifact:
    """Create a binary/media artifact.

    Binary artifacts are always blob-backed — ``inline_data`` is left empty and
    the raw bytes travel via ``binary_data``.  The API will store them directly
    in blob storage and compute ``size_bytes`` / ``sha256`` on ingest.
    """
    return TraceArtifact(
        artifact_type=artifact_type,
        storage_kind="blob",
        role=role,
        format="binary",
        mime_type=mime_type,
        filename=filename,
        preview_text=preview_text,
        metadata=metadata or {},
        step_id=step_id,
        binary_data=data,
    )


def attach_artifact(artifact: TraceArtifact) -> TraceArtifact:
    """Attach an artifact to the current run. Auto-sets step_id from context if not provided."""
    run = get_current_run()
    if run is None:
        return artifact

    if artifact.step_id is None:
        s = current_step()
        if s is not None:
            artifact.step_id = s.id

    if artifact.sequence_index is None:
        artifact.sequence_index = len(run.artifacts)

    run.artifacts.append(artifact)
    return artifact
