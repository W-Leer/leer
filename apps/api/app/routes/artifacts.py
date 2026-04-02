"""Artifact retrieval routes."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import get_blob_store
from app.schemas import ArtifactContentResponse
from app.services.reads import get_artifact_by_id
from app.storage.base import BlobStore

router = APIRouter(prefix="/v1")


@router.get("/artifacts/{artifact_id}", response_model=ArtifactContentResponse)
def get_artifact_content(
    artifact_id: UUID,
    session: Session = Depends(get_session),
    blob_store: BlobStore = Depends(get_blob_store),
) -> ArtifactContentResponse:
    artifact = get_artifact_by_id(session, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    data = _resolve_data(artifact, blob_store)

    return ArtifactContentResponse(
        id=artifact.id,
        artifact_type=artifact.artifact_type,
        role=artifact.role,
        format=artifact.format_,
        storage_kind=artifact.storage_kind,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        preview_text=artifact.preview_text,
        data=data,
    )


def _resolve_data(artifact, blob_store: BlobStore) -> dict | None:
    """Return the full artifact payload regardless of storage mode."""
    if artifact.storage_kind == "inline":
        return artifact.inline_data

    if artifact.storage_kind == "blob":
        if not artifact.blob_path:
            raise HTTPException(
                status_code=500,
                detail="Blob-backed artifact has no blob_path",
            )
        try:
            raw = blob_store.get(artifact.blob_path)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Artifact blob not found in storage",
            )
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
