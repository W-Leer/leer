"""Artifact retrieval routes."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import get_blob_store
from app.schemas import ArtifactContentResponse
from app.services.reads import get_artifact_by_id
from app.storage.base import BlobStore

router = APIRouter(prefix="/v1")

_BINARY_FORMAT = "binary"


def _is_binary(artifact) -> bool:
    return artifact.format_ == _BINARY_FORMAT


@router.get("/artifacts/{artifact_id}", response_model=ArtifactContentResponse)
def get_artifact_json(
    artifact_id: UUID,
    session: Session = Depends(get_session),
    blob_store: BlobStore = Depends(get_blob_store),
) -> ArtifactContentResponse:
    """Return artifact metadata + data as JSON.

    For binary artifacts ``data`` is ``None`` — use the
    ``/artifacts/{id}/content`` endpoint to fetch the raw bytes.
    """
    artifact = get_artifact_by_id(session, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    data = None if _is_binary(artifact) else _resolve_json_data(artifact, blob_store)

    return ArtifactContentResponse(
        id=artifact.id,
        artifact_type=artifact.artifact_type,
        role=artifact.role,
        format=artifact.format_,
        mime_type=artifact.mime_type,
        filename=artifact.filename,
        storage_kind=artifact.storage_kind,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        preview_text=artifact.preview_text,
        data=data,
    )


@router.get("/artifacts/{artifact_id}/content")
def get_artifact_raw_content(
    artifact_id: UUID,
    session: Session = Depends(get_session),
    blob_store: BlobStore = Depends(get_blob_store),
) -> Response:
    """Return the raw artifact content with the correct Content-Type.

    - Binary artifacts: raw bytes with their original MIME type.
    - JSON artifacts: the JSON blob with ``application/json``.
    """
    artifact = get_artifact_by_id(session, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if _is_binary(artifact):
        raw = _resolve_blob_bytes(artifact, blob_store)
        return Response(
            content=raw,
            media_type=artifact.mime_type or "application/octet-stream",
            headers={"Content-Length": str(len(raw))},
        )

    data = _resolve_json_data(artifact, blob_store)
    body = json.dumps(data).encode() if data is not None else b"null"
    return Response(content=body, media_type="application/json")


def _resolve_json_data(artifact, blob_store: BlobStore) -> dict | None:
    """Return the full JSON artifact payload regardless of storage mode."""
    if artifact.storage_kind == "inline":
        return artifact.inline_data

    if artifact.storage_kind == "blob":
        raw = _resolve_blob_bytes(artifact, blob_store)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(
                status_code=500,
                detail="Artifact blob is not valid JSON",
            )

    raise HTTPException(
        status_code=500,
        detail=f"Unknown storage_kind: {artifact.storage_kind}",
    )


def _resolve_blob_bytes(artifact, blob_store: BlobStore) -> bytes:
    """Load raw bytes from blob storage."""
    if not artifact.blob_path:
        raise HTTPException(
            status_code=500,
            detail="Blob-backed artifact has no blob_path",
        )
    try:
        return blob_store.get(artifact.blob_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Artifact blob not found in storage",
        )
