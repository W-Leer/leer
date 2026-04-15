"""Retrieval / RAG artifact helpers for Leer SDK.

Create canonical retrieval artifacts for each phase of a retrieval pipeline:
``retrieval_request``, ``retrieval_candidates``, ``retrieval_rerank``,
``retrieval_selected``, and ``retrieval_context``.

Artifact metadata is built via :func:`leer.metadata.retrieval_metadata` so
the canonical key set is defined in exactly one place.

All helpers produce ``TraceArtifact`` instances via the existing
``create_json_artifact`` / ``create_text_artifact`` plumbing.  Large
payloads (candidate sets, full context) go through the normal ingestion
pipeline and are blob-backed server-side when needed.

Usage::

    from leer.retrieval_artifacts import (
        create_retrieval_request_artifact,
        create_retrieval_candidates_artifact,
    )
    from leer import step, attach_artifact

    with step("vector_search", step_type="tool") as s:
        attach_artifact(create_retrieval_request_artifact(
            data={"query": "how does auth work?", "top_k": 10},
            retrieval_backend="pgvector",
            index_name="docs",
            step_id=s.id,
        ))
        results = search(...)
        attach_artifact(create_retrieval_candidates_artifact(
            data={"documents": results, "scores": scores},
            candidate_count=len(results),
            step_id=s.id,
        ))
"""

from __future__ import annotations

import json
from typing import Any

from leer.artifacts import create_json_artifact, create_text_artifact
from leer.metadata import retrieval_metadata as _retrieval_metadata
from leer.models import TraceArtifact


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_retrieval_request_artifact(
    data: dict[str, Any] | list[Any],
    *,
    step_id: str | None = None,
    retrieval_backend: str | None = None,
    index_name: str | None = None,
    query_text: str | None = None,
    parent_llm_step_id: str | None = None,
) -> TraceArtifact:
    """Create a ``retrieval_request`` artifact for the query/filter payload."""
    return create_json_artifact(
        artifact_type="retrieval_request",
        role="input",
        data=data,
        preview_text=_json_preview(data),
        metadata=_artifact_meta(
            retrieval_stage="request",
            retrieval_backend=retrieval_backend,
            index_name=index_name,
            query_text=query_text,
            parent_llm_step_id=parent_llm_step_id,
        ),
        step_id=step_id,
    )


def create_retrieval_candidates_artifact(
    data: dict[str, Any] | list[Any],
    *,
    step_id: str | None = None,
    candidate_count: int | None = None,
    retrieval_backend: str | None = None,
    index_name: str | None = None,
    parent_llm_step_id: str | None = None,
) -> TraceArtifact:
    """Create a ``retrieval_candidates`` artifact for the initial result set.

    Candidate sets may be large — the normal ingestion pipeline will
    blob-back them server-side when they exceed the inline threshold.
    """
    preview = f"{candidate_count} candidates" if candidate_count is not None else _json_preview(data)
    return create_json_artifact(
        artifact_type="retrieval_candidates",
        role="output",
        data=data,
        preview_text=preview,
        metadata=_artifact_meta(
            retrieval_stage="candidates",
            candidate_count=candidate_count,
            retrieval_backend=retrieval_backend,
            index_name=index_name,
            parent_llm_step_id=parent_llm_step_id,
        ),
        step_id=step_id,
    )


def create_retrieval_rerank_artifact(
    data: dict[str, Any] | list[Any],
    *,
    step_id: str | None = None,
    candidate_count: int | None = None,
    selected_count: int | None = None,
    retrieval_backend: str | None = None,
    parent_llm_step_id: str | None = None,
) -> TraceArtifact:
    """Create a ``retrieval_rerank`` artifact for reranked candidates."""
    return create_json_artifact(
        artifact_type="retrieval_rerank",
        role="output",
        data=data,
        preview_text=_json_preview(data),
        metadata=_artifact_meta(
            retrieval_stage="rerank",
            candidate_count=candidate_count,
            selected_count=selected_count,
            retrieval_backend=retrieval_backend,
            parent_llm_step_id=parent_llm_step_id,
        ),
        step_id=step_id,
    )


def create_retrieval_selected_artifact(
    data: dict[str, Any] | list[Any],
    *,
    step_id: str | None = None,
    selected_count: int | None = None,
    retrieval_backend: str | None = None,
    index_name: str | None = None,
    parent_llm_step_id: str | None = None,
) -> TraceArtifact:
    """Create a ``retrieval_selected`` artifact for the chosen subset."""
    preview = f"{selected_count} selected" if selected_count is not None else _json_preview(data)
    return create_json_artifact(
        artifact_type="retrieval_selected",
        role="output",
        data=data,
        preview_text=preview,
        metadata=_artifact_meta(
            retrieval_stage="selected",
            selected_count=selected_count,
            retrieval_backend=retrieval_backend,
            index_name=index_name,
            parent_llm_step_id=parent_llm_step_id,
        ),
        step_id=step_id,
    )


def create_retrieval_context_artifact(
    data: dict[str, Any] | list[Any] | str,
    *,
    step_id: str | None = None,
    context_token_estimate: int | None = None,
    selected_count: int | None = None,
    parent_llm_step_id: str | None = None,
) -> TraceArtifact:
    """Create a ``retrieval_context`` artifact for the final packed context.

    If *data* is a ``str``, the artifact is stored via
    :func:`create_text_artifact` (``format="text"``).  Otherwise it is
    stored as JSON via :func:`create_json_artifact`.
    """
    meta = _artifact_meta(
        retrieval_stage="context",
        context_token_estimate=context_token_estimate,
        selected_count=selected_count,
        parent_llm_step_id=parent_llm_step_id,
    )

    if isinstance(data, str):
        return create_text_artifact(
            artifact_type="retrieval_context",
            role="output",
            text=data,
            preview_text=data[:200],
            metadata=meta,
            step_id=step_id,
        )

    return create_json_artifact(
        artifact_type="retrieval_context",
        role="output",
        data=data,
        preview_text=_json_preview(data),
        metadata=meta,
        step_id=step_id,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _artifact_meta(**kwargs: Any) -> dict[str, Any]:
    """Build artifact metadata by delegating to the Step 1 canonical helper.

    Uses ``retrieval_metadata()`` as the single source of truth for key
    names and ``capability_kind="retrieval"`` injection.
    """
    return _retrieval_metadata(**kwargs)


def _json_preview(data: Any, max_len: int = 200) -> str:
    try:
        return json.dumps(data, default=str)[:max_len]
    except Exception:
        return str(data)[:max_len]
