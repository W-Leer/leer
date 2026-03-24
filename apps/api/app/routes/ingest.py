from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import IngestRunRequest, IngestRunResponse
from app.services.ingestion import ingest_run

router = APIRouter(prefix="/v1/ingest")


@router.post("/runs", response_model=IngestRunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    request: IngestRunRequest,
    session: Session = Depends(get_session),
) -> IngestRunResponse:
    try:
        run_id = ingest_run(session, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestRunResponse(run_id=run_id)
