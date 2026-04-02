from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.dependencies import get_blob_store
from app.schemas import IngestRunRequest, IngestRunResponse
from app.services.ingestion import ingest_run
from app.storage.base import BlobStore

router = APIRouter(prefix="/v1/ingest")


@router.post("/runs", response_model=IngestRunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    request: IngestRunRequest,
    session: Session = Depends(get_session),
    blob_store: BlobStore = Depends(get_blob_store),
) -> IngestRunResponse:
    try:
        threshold = get_settings().blob_inline_threshold_bytes
        run_id = ingest_run(
            session,
            request,
            blob_store=blob_store,
            threshold=threshold,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestRunResponse(run_id=run_id)
